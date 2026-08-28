from ecos_release.generator import generate_installer

from tests.support import build_release_assets, make_model, start_server, default_routes, server_base


def test_identical_input_produces_identical_bytes():
    assets = build_release_assets()
    server = start_server(default_routes(assets))
    try:
        model = make_model(assets, server_base(server))
        first = generate_installer(model)
        second = generate_installer(model)
    finally:
        server.shutdown()
    assert first == second
    assert first.startswith("#!/bin/sh\n")
    assert f'ECC_VERSION="{model.ecc_version}"' in first
    assert model.ecc.sha256 in first
    assert model.ecc_cnb_url in first
    assert model.oss_cad.cnb_url in first
    assert "CHIPCOMPILER_OSS_CAD_DIR" in first
    assert "[[ " not in first
    assert "BASH_SOURCE" not in first
    assert "\nsource " not in first


def test_generated_installer_embeds_liberty_inventory():
    assets = build_release_assets()
    server = start_server(default_routes(assets))
    try:
        model = make_model(assets, server_base(server))
        text = generate_installer(model)
    finally:
        server.shutdown()
    for path in model.pdk_liberty_files:
        assert path in text
    for asset in model.pdk_supplemental:
        assert asset.name in text
        assert asset.dest in text
        assert asset.cnb_url in text
