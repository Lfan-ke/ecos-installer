"""Assemble a validated release model from GitHub metadata and local archives."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from ecos_release.archive import liberty_destinations, validate_archive
from ecos_release.github import fetch_release, select_ecc_asset
from ecos_release.model import (
    Asset,
    InvalidReleaseModel,
    ReleaseModel,
    assets_from_pdk_metadata,
    load_toolchain_metadata,
)

LIBERTY_KINDS = {"liberty"}


def cnb_url(template: str, *, tag: str, name: str) -> str:
    return template.format(tag=tag, name=name)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path, *, timeout: int = 60) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "ecos-release"})
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as fh:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    return destination


def verify_digest(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise InvalidReleaseModel(
            f"digest mismatch for {path.name}: expected {expected}, got {actual}"
        )


def assemble_release_model(
    tag: str,
    *,
    metadata_path: Path,
    archive_dir: Path | None = None,
    github_token: str | None = None,
    ecc_cnb_url: str | None = None,
    pdk_base_sha256: str | None = None,
    pdk_liberty_files: tuple[str, ...] | None = None,
    validate_archives: bool = False,
    verify_cnb: bool = False,
) -> ReleaseModel:
    metadata = load_toolchain_metadata(metadata_path)
    ecc_meta = metadata["ecc"]
    repo = ecc_meta["github_repo"]
    release = fetch_release(repo, tag, token=github_token)
    ecc_asset = select_ecc_asset(release, name=ecc_meta["asset_name"])
    resolved_cnb = ecc_cnb_url or cnb_url(
        ecc_meta["cnb_url_template"], tag=tag, name=ecc_asset.name
    )
    oss = metadata["oss_cad_suite"]
    pdk = metadata["pdk"]
    supplemental = assets_from_pdk_metadata(metadata)
    liberty_files = pdk_liberty_files
    base_sha = pdk_base_sha256
    if validate_archives:
        if archive_dir is None:
            raise InvalidReleaseModel("archive_dir is required when validating archives")
        archive_dir.mkdir(parents=True, exist_ok=True)
        ecc_path = archive_dir / ecc_asset.name
        download_file(ecc_asset.url, ecc_path)
        verify_digest(ecc_path, ecc_asset.sha256)
        validate_archive(ecc_path)
        if verify_cnb:
            cnb_path = archive_dir / f"cnb-{ecc_asset.name}"
            download_file(resolved_cnb, cnb_path)
            verify_digest(cnb_path, ecc_asset.sha256)
        oss_path = archive_dir / oss["name"]
        download_file(oss["url"], oss_path)
        verify_digest(oss_path, oss["sha256"])
        validate_archive(oss_path)
        base_path = archive_dir / pdk["base_name"]
        download_file(pdk["base_url"], base_path)
        base_sha = sha256_file(base_path)
        validate_archive(base_path)
        collected: list[str] = []
        for asset in supplemental:
            path = archive_dir / asset.name
            download_file(asset.url, path)
            verify_digest(path, asset.sha256)
            inventory = validate_archive(
                path, require_liberty=asset.kind in LIBERTY_KINDS
            )
            if asset.kind in LIBERTY_KINDS:
                if not asset.dest:
                    raise InvalidReleaseModel(f"Liberty asset {asset.name} is missing dest")
                collected.extend(liberty_destinations(asset.dest, inventory.liberty_files))
        liberty_files = tuple(sorted(set(collected)))
    if not base_sha:
        raise InvalidReleaseModel("PDK base archive SHA-256 is required")
    if not liberty_files:
        raise InvalidReleaseModel("PDK Liberty inventory is required")
    version = tag[1:] if tag.startswith("v") else tag
    return ReleaseModel(
        ecc_version=version,
        ecc_tag=tag if tag.startswith("v") else f"v{tag}",
        ecc=Asset(
            name=ecc_asset.name,
            url=ecc_asset.url,
            sha256=ecc_asset.sha256,
            size=ecc_asset.size,
        ),
        ecc_cnb_url=resolved_cnb,
        oss_cad_version=str(oss["version"]),
        oss_cad=Asset(
            name=oss["name"],
            url=oss["url"],
            sha256=oss["sha256"],
            size=oss.get("size"),
            cnb_url=str(oss.get("cnb_url", "")),
        ),
        pdk_version=str(pdk["version"]),
        pdk_base=Asset(
            name=pdk["base_name"],
            url=pdk["base_url"],
            sha256=base_sha,
            cnb_url=str(pdk.get("cnb_url", "")),
        ),
        pdk_supplemental=supplemental,
        pdk_liberty_files=tuple(liberty_files),
        pdk_tech_lef=str(pdk["tech_lef"]),
        pdk_cell_lefs=tuple(pdk["cell_lefs"]),
    )
