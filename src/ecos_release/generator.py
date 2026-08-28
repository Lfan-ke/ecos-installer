"""Render a self-contained POSIX ECC installer from a validated release model."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from ecos_release.model import ReleaseModel

PLACEHOLDERS = (
    "ECC_VERSION",
    "ECC_TAG",
    "ECC_ASSET_NAME",
    "ECC_SHA256",
    "ECC_SIZE",
    "ECC_GITHUB_URL",
    "ECC_CNB_URL",
    "MIN_GLIBC_MAJOR",
    "MIN_GLIBC_MINOR",
    "OSS_CAD_VERSION",
    "OSS_CAD_ASSET_NAME",
    "OSS_CAD_SHA256",
    "OSS_CAD_URL",
    "PDK_NAME",
    "PDK_VERSION",
    "PDK_BASE_ASSET_NAME",
    "PDK_BASE_SHA256",
    "PDK_BASE_URL",
    "PDK_TECH_LEF",
    "PDK_CELL_LEFS",
    "PDK_ASSET_TABLE",
    "PDK_LIBERTY_FILES",
)


def generate_installer(model: ReleaseModel) -> str:
    template = _load_template()
    mapping = {
        "ECC_VERSION": model.ecc_version,
        "ECC_TAG": model.ecc_tag,
        "ECC_ASSET_NAME": model.ecc.name,
        "ECC_SHA256": model.ecc.sha256,
        "ECC_SIZE": "" if model.ecc.size is None else str(model.ecc.size),
        "ECC_GITHUB_URL": model.ecc.url,
        "ECC_CNB_URL": model.ecc_cnb_url,
        "MIN_GLIBC_MAJOR": str(model.min_glibc[0]),
        "MIN_GLIBC_MINOR": str(model.min_glibc[1]),
        "OSS_CAD_VERSION": model.oss_cad_version,
        "OSS_CAD_ASSET_NAME": model.oss_cad.name,
        "OSS_CAD_SHA256": model.oss_cad.sha256,
        "OSS_CAD_URL": model.oss_cad.url,
        "PDK_NAME": model.pdk_name,
        "PDK_VERSION": model.pdk_version,
        "PDK_BASE_ASSET_NAME": model.pdk_base.name,
        "PDK_BASE_SHA256": model.pdk_base.sha256,
        "PDK_BASE_URL": model.pdk_base.url,
        "PDK_TECH_LEF": model.pdk_tech_lef,
        "PDK_CELL_LEFS": _join_lines(model.pdk_cell_lefs),
        "PDK_ASSET_TABLE": _asset_table(model),
        "PDK_LIBERTY_FILES": _join_lines(model.pdk_liberty_files),
    }
    rendered = template
    for key in PLACEHOLDERS:
        rendered = rendered.replace(f"@{key}@", mapping[key])
    leftover = [key for key in PLACEHOLDERS if f"@{key}@" in rendered]
    if leftover:
        raise RuntimeError(f"unsubstituted installer placeholders: {leftover}")
    if "@" in rendered and _has_placeholder(rendered):
        raise RuntimeError("unsubstituted installer placeholder remains")
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered.replace("\r\n", "\n")


def write_installer(model: ReleaseModel, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = generate_installer(model)
    destination.write_bytes(text.encode("utf-8"))
    return destination


def _load_template() -> str:
    return resources.files("ecos_release").joinpath("templates/ecc-installer.sh.in").read_text(
        encoding="utf-8"
    )


def _asset_table(model: ReleaseModel) -> str:
    rows = []
    for asset in model.pdk_supplemental:
        if not asset.dest:
            raise RuntimeError(f"PDK asset {asset.name} is missing dest")
        rows.append("\t".join((asset.name, asset.sha256, asset.url, asset.dest)))
    return "\n".join(rows)


def _join_lines(values: tuple[str, ...]) -> str:
    return "\n".join(values)


def _has_placeholder(text: str) -> bool:
    start = text.find("@")
    while start != -1:
        end = text.find("@", start + 1)
        if end == -1:
            return False
        token = text[start + 1 : end]
        if token.isupper() and all(ch.isalpha() or ch == "_" for ch in token) and token:
            return True
        start = text.find("@", start + 1)
    return False
