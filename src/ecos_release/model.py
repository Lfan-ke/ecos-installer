"""Validated release model used to generate an ECC installer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ecos_release.semver import InvalidVersion, parse, parse_tag

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
LIBERTY_ARCHIVE_NAMES = (
    "ics55_LLSC_H7CH_liberty.tar.bz2",
    "ics55_LLSC_H7CL_liberty.tar.bz2",
    "ics55_LLSC_H7CR_liberty.tar.bz2",
)
SUPPORTED_OS = "linux"
SUPPORTED_CPU = "x86_64"
MIN_GLIBC = (2, 34)
ECC_ASSET_NAME = "ecc-cli-linux-x86_64.tar.gz"


class InvalidReleaseModel(ValueError):
    """Raised when installer generation input is incomplete or inconsistent."""


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    sha256: str
    size: int | None = None
    dest: str | None = None
    kind: str = "archive"

    def __post_init__(self) -> None:
        if not self.name or "/" in self.name or "\\" in self.name:
            raise InvalidReleaseModel(f"invalid asset name: {self.name!r}")
        if not self.url:
            raise InvalidReleaseModel(f"missing URL for asset {self.name}")
        if not SHA256_RE.match(self.sha256):
            raise InvalidReleaseModel(
                f"invalid SHA-256 for {self.name}: {self.sha256!r}"
            )
        if self.size is not None and self.size < 0:
            raise InvalidReleaseModel(f"negative size for {self.name}")
        if self.dest is not None:
            _require_relative_dest(self.dest, self.name)


@dataclass(frozen=True)
class ReleaseModel:
    ecc_version: str
    ecc_tag: str
    ecc: Asset
    ecc_cnb_url: str
    oss_cad_version: str
    oss_cad: Asset
    pdk_version: str
    pdk_base: Asset
    pdk_supplemental: tuple[Asset, ...]
    pdk_liberty_files: tuple[str, ...]
    pdk_tech_lef: str
    pdk_cell_lefs: tuple[str, ...]
    os_name: str = SUPPORTED_OS
    cpu: str = SUPPORTED_CPU
    min_glibc: tuple[int, int] = MIN_GLIBC
    pdk_name: str = "icsprout55"

    def __post_init__(self) -> None:
        validate_release_model(self)


def validate_release_model(model: ReleaseModel) -> None:
    try:
        version = parse(model.ecc_version)
        tag_version = parse_tag(model.ecc_tag)
    except InvalidVersion as exc:
        raise InvalidReleaseModel(str(exc)) from exc
    if version != tag_version or model.ecc_tag != f"v{model.ecc_version}":
        raise InvalidReleaseModel(
            f"tag {model.ecc_tag!r} does not match version {model.ecc_version!r}"
        )
    if model.os_name != SUPPORTED_OS or model.cpu != SUPPORTED_CPU:
        raise InvalidReleaseModel(
            f"unsupported platform {model.os_name}/{model.cpu}; "
            f"first installer supports {SUPPORTED_OS}/{SUPPORTED_CPU}"
        )
    if model.min_glibc != MIN_GLIBC:
        raise InvalidReleaseModel(
            f"unsupported minimum glibc {model.min_glibc}; expected {MIN_GLIBC}"
        )
    if model.ecc.name != ECC_ASSET_NAME:
        raise InvalidReleaseModel(
            f"ECC asset must be named {ECC_ASSET_NAME}, got {model.ecc.name!r}"
        )
    if not model.ecc_cnb_url:
        raise InvalidReleaseModel("missing CNB URL for ECC asset")
    if not model.oss_cad_version:
        raise InvalidReleaseModel("missing OSS CAD Suite version")
    if not model.pdk_version:
        raise InvalidReleaseModel("missing ICS55 PDK version")
    if len(model.pdk_supplemental) != 7:
        raise InvalidReleaseModel(
            f"ICS55 PDK requires 7 supplemental assets, got {len(model.pdk_supplemental)}"
        )
    names = [asset.name for asset in model.pdk_supplemental]
    if len(set(names)) != 7:
        raise InvalidReleaseModel("PDK supplemental asset names must be unique")
    for required in LIBERTY_ARCHIVE_NAMES:
        if required not in names:
            raise InvalidReleaseModel(f"missing Liberty archive {required}")
    if not model.pdk_liberty_files:
        raise InvalidReleaseModel("PDK Liberty inventory is empty")
    for path in model.pdk_liberty_files:
        _require_relative_dest(path, "liberty")
        if not path.endswith(".lib"):
            raise InvalidReleaseModel(f"Liberty path does not end in .lib: {path}")
    _require_relative_dest(model.pdk_tech_lef, "tech lef")
    if len(model.pdk_cell_lefs) < 2:
        raise InvalidReleaseModel("PDK standard-cell LEF list is incomplete")
    for path in model.pdk_cell_lefs:
        _require_relative_dest(path, "cell lef")


def parse_digest(value: str) -> str:
    match = DIGEST_RE.match(value.strip())
    if match is None:
        raise InvalidReleaseModel(f"digest must match sha256:[0-9a-f]{{64}}, got {value!r}")
    return match.group(1)


def _require_relative_dest(path: str, label: str) -> None:
    if not path or path.startswith("/") or path.startswith("\\"):
        raise InvalidReleaseModel(f"absolute or empty {label} path: {path!r}")
    if "\x00" in path or any(ord(ch) < 32 for ch in path):
        raise InvalidReleaseModel(f"control character in {label} path: {path!r}")
    parts = Path(path).parts
    if any(part in ("", ".", "..") for part in parts):
        raise InvalidReleaseModel(f"unsafe {label} path: {path!r}")


def load_toolchain_metadata(path: Path) -> dict[str, Any]:
    import tomllib

    with path.open("rb") as fh:
        return tomllib.load(fh)


def assets_from_pdk_metadata(data: dict[str, Any]) -> tuple[Asset, ...]:
    assets = []
    for item in data["pdk"]["assets"]:
        assets.append(
            Asset(
                name=item["name"],
                url=item["url"],
                sha256=item["sha256"],
                size=item.get("size"),
                dest=item["dest"],
                kind=item.get("kind", "archive"),
            )
        )
    return tuple(assets)
