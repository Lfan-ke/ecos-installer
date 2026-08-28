from ecos_release.model import Asset, InvalidReleaseModel, ReleaseModel, parse_digest

import pytest

from tests.support import CELL_LEFS, TECH_LEF, liberty_paths


def _asset(name: str = "ecc-cli-linux-x86_64.tar.gz", **kwargs) -> Asset:
    values = {
        "name": name,
        "url": f"https://example.test/{name}",
        "sha256": "a" * 64,
        "size": 1,
    }
    values.update(kwargs)
    return Asset(**values)


def _supplemental() -> tuple[Asset, ...]:
    names = [
        "ics55_LLSC_H7CH_liberty.tar.bz2",
        "ics55_LLSC_H7CL_liberty.tar.bz2",
        "ics55_LLSC_H7CR_liberty.tar.bz2",
        "ics55_LLSC_H7CH_gds.tar.bz2",
        "ics55_LLSC_H7CL_gds.tar.bz2",
        "ics55_LLSC_H7CR_gds.tar.bz2",
        "ICsprout_55LLULP1233_IO_251013_gds.tar.bz2",
    ]
    dests = [
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CH/liberty",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL/liberty",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR/liberty",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CH/gds",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL/gds",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR/gds",
        "IP/IO/ICsprout_55LLULP1233_IO_251013/gds",
    ]
    return tuple(
        _asset(name, dest=dest, kind="liberty" if "liberty" in name else "gds")
        for name, dest in zip(names, dests, strict=True)
    )


def valid_model(**kwargs) -> ReleaseModel:
    values = {
        "ecc_version": "0.1.0-alpha.11",
        "ecc_tag": "v0.1.0-alpha.11",
        "ecc": _asset(),
        "ecc_cnb_url": "https://cnb.example/ecc-cli-linux-x86_64.tar.gz",
        "oss_cad_version": "20260827",
        "oss_cad": _asset("oss-cad-suite-linux-x64-20260827.tgz"),
        "pdk_version": "v1.10.102",
        "pdk_base": _asset("icsprout55-pdk-v1.10.102.tar.gz"),
        "pdk_supplemental": _supplemental(),
        "pdk_liberty_files": liberty_paths(),
        "pdk_tech_lef": TECH_LEF,
        "pdk_cell_lefs": CELL_LEFS,
    }
    values.update(kwargs)
    return ReleaseModel(**values)


def test_valid_model_accepts_first_platform():
    model = valid_model()
    assert model.ecc_tag == "v0.1.0-alpha.11"


def test_rejects_inconsistent_tag():
    with pytest.raises(InvalidReleaseModel):
        valid_model(ecc_tag="v0.1.0-alpha.10")


def test_rejects_invalid_digest():
    with pytest.raises(InvalidReleaseModel):
        parse_digest("sha256:xyz")
    with pytest.raises(InvalidReleaseModel):
        _asset(sha256="deadbeef")


def test_rejects_missing_cnb_and_wrong_asset_name():
    with pytest.raises(InvalidReleaseModel):
        valid_model(ecc_cnb_url="")
    with pytest.raises(InvalidReleaseModel):
        valid_model(ecc=_asset("ecc-linux.tar.gz"))


def test_rejects_unsupported_platform_and_incomplete_pdk():
    with pytest.raises(InvalidReleaseModel):
        valid_model(os_name="darwin")
    with pytest.raises(InvalidReleaseModel):
        valid_model(pdk_supplemental=_supplemental()[:6])
    with pytest.raises(InvalidReleaseModel):
        valid_model(pdk_liberty_files=())
