import shutil
import subprocess
from pathlib import Path

import pytest

from ecos_release.generator import generate_installer
from tests.support import build_release_assets, default_routes, make_model, server_base, start_server


@pytest.fixture(scope="module")
def installer_text() -> str:
    assets = build_release_assets()
    server = start_server(default_routes(assets))
    try:
        return generate_installer(make_model(assets, server_base(server)))
    finally:
        server.shutdown()


def test_dash_and_bash_syntax(tmp_path: Path, installer_text: str):
    path = tmp_path / "ecc-installer.sh"
    path.write_text(installer_text)
    shells = []
    if shutil.which("dash"):
        shells.append("dash")
    if shutil.which("bash"):
        shells.append("bash")
    if not shells:
        pytest.skip("dash and bash are unavailable")
    for shell in shells:
        result = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{shell} -n failed: {result.stderr}"


def test_shellcheck_when_available(tmp_path: Path, installer_text: str):
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        pytest.skip("shellcheck is not installed")
    path = tmp_path / "ecc-installer.sh"
    path.write_text(installer_text)
    result = subprocess.run(
        [shellcheck, "-s", "dash", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
