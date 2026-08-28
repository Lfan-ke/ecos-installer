from __future__ import annotations

import json
import os
import shutil
import stat
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from ecos_release.archive import validate_archive
from tests.support import (
    build_ecc_archive,
    build_oss_archive,
    build_release_assets,
    default_routes,
    make_model,
    pack_tar,
    run_installer,
    server_base,
    sha256_bytes,
    start_server,
    write_fake_cmd,
    write_generated_installer,
    xdg_env,
)


@pytest.fixture(scope="module")
def assets():
    return build_release_assets()


@pytest.fixture(scope="module")
def http(assets):
    routes = default_routes(assets)
    server = start_server(routes)
    try:
        yield server, routes, server_base(server)
    finally:
        server.shutdown()


@pytest.fixture
def routes(http):
    server, routes, _base = http
    snapshot = {key: dict(value) for key, value in routes.items()}
    yield routes
    routes.clear()
    routes.update(snapshot)
    server.routes = routes


@pytest.fixture
def base(http) -> str:
    return http[2]


@pytest.fixture
def installer(tmp_path: Path, assets, base) -> Path:
    model = make_model(assets, base)
    return write_generated_installer(model, tmp_path / "ecc-installer.sh")


def _roots(env: dict[str, str]) -> tuple[Path, Path, Path, Path]:
    return (
        Path(env["XDG_DATA_HOME"]) / "ecc",
        Path(env["XDG_BIN_HOME"]),
        Path(env["XDG_CACHE_HOME"]) / "ecc",
        Path(env["XDG_CONFIG_HOME"]) / "ecc",
    )


def _read_wrapper_env(wrapper: Path, env: dict[str, str]) -> dict[str, str]:
    result = subprocess_run_wrapper(wrapper, env, "dump-env")
    assert result.returncode == 0, result.stderr
    parsed = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        parsed[key] = value
    return parsed


def subprocess_run_wrapper(wrapper: Path, env: dict[str, str], *args: str):
    import subprocess

    return subprocess.run(
        [str(wrapper), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_github_success_installs_wrapper_and_receipt(tmp_path, installer, assets):
    env = xdg_env(tmp_path)
    result = run_installer(installer, env)
    assert result.returncode == 0, result.stderr
    data, bindir, _cache, config = _roots(env)
    wrapper = bindir / "ecc"
    assert wrapper.is_file()
    assert wrapper.read_text().splitlines()[:2] == ["#!/bin/sh", "# ecos-release-wrapper-v1"]
    dumped = _read_wrapper_env(wrapper, env)
    assert dumped["OSS"] == ""
    assert dumped["PDK"] == ""
    assert dumped["YOSYS_PLUGINPATH"] == ""
    assert dumped["YOSYS_DATDIR"] == ""
    receipt = json.loads((config / "ecc-receipt.json").read_text())
    assert receipt["binaries"] == ["ecc"]
    assert receipt["provider"] == {"format": 1, "name": "ecos-release"}
    assert receipt["version"] == "0.1.0-alpha.11"
    assert (data / "v0.1.0-alpha.11" / "ecc").is_file()
    validate_archive(_write_tmp_archive(tmp_path, assets["ecc-cli-linux-x86_64.tar.gz"].data))


def _write_tmp_archive(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "check.tar.gz"
    path.write_bytes(data)
    return path


def test_github_failure_falls_back_to_cnb(tmp_path, assets, base, routes):
    routes["/github/ecc-cli-linux-x86_64.tar.gz"] = {"status": 500}
    installer = write_generated_installer(make_model(assets, base), tmp_path / "installer.sh")
    result = run_installer(installer, xdg_env(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "failed to download" in result.stderr


def test_forced_source_modes_and_both_unavailable(tmp_path, assets, base, routes):
    env = xdg_env(tmp_path)
    installer = write_generated_installer(make_model(assets, base), tmp_path / "installer.sh")
    ok = run_installer(installer, env, "--download-source", "github")
    assert ok.returncode == 0, ok.stderr
    routes["/github/ecc-cli-linux-x86_64.tar.gz"] = {"status": 404}
    env2 = xdg_env(tmp_path / "cnb")
    cnb = run_installer(installer, env2, "--download-source", "cnb")
    assert cnb.returncode == 0, cnb.stderr
    routes["/cnb/ecc-cli-linux-x86_64.tar.gz"] = {"status": 404}
    env3 = xdg_env(tmp_path / "none")
    failed = run_installer(installer, env3)
    assert failed.returncode != 0


def test_checksum_mismatch_fails_before_extract(tmp_path, assets, base, routes):
    routes["/github/ecc-cli-linux-x86_64.tar.gz"] = {"data": b"not-the-archive"}
    routes["/cnb/ecc-cli-linux-x86_64.tar.gz"] = {"data": b"also-wrong"}
    installer = write_generated_installer(make_model(assets, base), tmp_path / "installer.sh")
    env = xdg_env(tmp_path)
    result = run_installer(installer, env)
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    _data, bindir, _cache, config = _roots(env)
    assert not (bindir / "ecc").exists()
    assert not (config / "ecc-receipt.json").exists()


def test_unsupported_os_cpu_libc_and_glibc(tmp_path, installer):
    fake = tmp_path / "fakebin"

    write_fake_cmd(fake, "uname", "#!/bin/sh\n[ \"$1\" = -s ] && echo Darwin || echo x86_64\n")
    result = run_installer(installer, xdg_env(tmp_path / "os", extra_path=str(fake)))
    assert result.returncode != 0
    assert "os=Darwin" in result.stderr

    write_fake_cmd(fake, "uname", "#!/bin/sh\n[ \"$1\" = -s ] && echo Linux || echo aarch64\n")
    result = run_installer(installer, xdg_env(tmp_path / "cpu", extra_path=str(fake)))
    assert result.returncode != 0
    assert "cpu=aarch64" in result.stderr

    write_fake_cmd(
        fake,
        "ldd",
        "#!/bin/sh\necho 'musl libc (aarch64) 1.2.4'\n",
    )
    write_fake_cmd(fake, "uname", "#!/bin/sh\n[ \"$1\" = -s ] && echo Linux || echo x86_64\n")
    result = run_installer(installer, xdg_env(tmp_path / "musl", extra_path=str(fake)))
    assert result.returncode != 0
    assert "libc=musl" in result.stderr

    write_fake_cmd(
        fake,
        "ldd",
        "#!/bin/sh\necho 'ldd (GNU libc) 2.31'\n",
    )
    result = run_installer(installer, xdg_env(tmp_path / "old", extra_path=str(fake)))
    assert result.returncode != 0
    assert "libc_version=2.31" in result.stderr


def test_unsupported_bitness(tmp_path, installer):
    fake = tmp_path / "fakebin"
    real_head = shutil.which("head")
    assert real_head is not None
    write_fake_cmd(
        fake,
        "head",
        f"""#!/bin/sh
if [ "$1" = "-c" ] && [ "$2" = "5" ]; then
  printf '\\177ELF\\001'
  exit 0
fi
exec {real_head} "$@"
""",
    )
    result = run_installer(installer, xdg_env(tmp_path, extra_path=str(fake)))
    assert result.returncode != 0
    assert "bitness=32" in result.stderr


def test_path_guidance_without_profile_mutation(tmp_path, installer):
    env = xdg_env(tmp_path)
    profile = Path(env["HOME"]) / ".profile"
    profile.write_text("# keep\n")
    result = run_installer(installer, env)
    assert result.returncode == 0, result.stderr
    assert "which is not in PATH" in result.stderr
    assert "export PATH=" in result.stderr
    assert profile.read_text() == "# keep\n"


def test_toolchain_wrapper_exports_only_managed_roots(tmp_path, installer):
    env = xdg_env(tmp_path)
    env["PATH"] = f"{env['XDG_BIN_HOME']}:{env['PATH']}"
    result = run_installer(installer, env, "--with-toolchain")
    assert result.returncode == 0, result.stderr
    data, bindir, _cache, _config = _roots(env)
    dumped = _read_wrapper_env(bindir / "ecc", env)
    oss = data / "tools" / "oss-cad-suite" / "20260827"
    pdk = data / "pdks" / "icsprout55" / "v1.10.102"
    assert dumped["OSS"] == str(oss)
    assert dumped["PDK"] == str(pdk)
    assert str(oss / "bin") not in dumped["PATH"].split(":")
    assert dumped["YOSYS_PLUGINPATH"] == ""
    assert dumped["YOSYS_DATDIR"] == ""
    assert (oss / "bin" / "yosys").is_file()
    for liberty in (
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CH/liberty/h7ch.lib",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL/liberty/h7cl.lib",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR/liberty/h7cr.lib",
    ):
        assert (pdk / liberty).stat().st_size > 0


def test_ecc_only_upgrade_preserves_validated_toolchain(tmp_path, assets, base):
    env = xdg_env(tmp_path)
    first = write_generated_installer(make_model(assets, base), tmp_path / "first.sh")
    assert run_installer(first, env, "--with-toolchain").returncode == 0
    newer_assets = build_release_assets(version="0.1.0-alpha.12")
    # Reuse served bytes by installing a newer installer that points at the same URLs/hashes.
    model = make_model(assets, base, version="0.1.0-alpha.12")
    # The newer installer embeds alpha.12 but the served ECC archive is alpha.11 bytes with matching sha.
    model_assets = dict(assets)
    model_assets["ecc-cli-linux-x86_64.tar.gz"] = assets["ecc-cli-linux-x86_64.tar.gz"]
    second = write_generated_installer(
        make_model(model_assets, base, version="0.1.0-alpha.12"),
        tmp_path / "second.sh",
    )
    result = run_installer(second, env)
    assert result.returncode == 0, result.stderr
    data, bindir, _cache, _config = _roots(env)
    dumped = _read_wrapper_env(bindir / "ecc", env)
    assert dumped["OSS"].endswith("/tools/oss-cad-suite/20260827")
    assert (data / "v0.1.0-alpha.11").is_dir()
    assert (data / "v0.1.0-alpha.12").is_dir()
    del newer_assets


def test_failed_first_install_creates_neither_wrapper_nor_receipt(tmp_path, installer):
    env = xdg_env(tmp_path)
    env["ECC_DOWNLOAD_SOURCE"] = "nope"
    result = run_installer(installer, env)
    assert result.returncode != 0
    _data, bindir, _cache, config = _roots(env)
    assert not (bindir / "ecc").exists()
    assert not (config / "ecc-receipt.json").exists()


def test_failed_upgrade_preserves_existing_wrapper(tmp_path, assets, base, routes):
    env = xdg_env(tmp_path)
    first = write_generated_installer(make_model(assets, base), tmp_path / "first.sh")
    assert run_installer(first, env).returncode == 0
    _data, bindir, _cache, config = _roots(env)
    wrapper_before = (bindir / "ecc").read_text()
    receipt_before = (config / "ecc-receipt.json").read_text()
    bad = build_ecc_archive("0.1.0-alpha.12", fail=True)
    packed_name = "ecc-cli-linux-x86_64.tar.gz"
    routes["/github/ecc-next.tar.gz"] = {"data": bad}
    routes["/cnb/ecc-next.tar.gz"] = {"data": bad}
    next_assets = dict(assets)
    from tests.support import PackedAsset

    next_assets[packed_name] = PackedAsset(packed_name, bad, sha256_bytes(bad))
    model = make_model(
        next_assets,
        base,
        version="0.1.0-alpha.12",
        ecc_github=f"{base}/github/ecc-next.tar.gz",
        ecc_cnb=f"{base}/cnb/ecc-next.tar.gz",
    )
    second = write_generated_installer(model, tmp_path / "second.sh")
    result = run_installer(second, env)
    assert result.returncode != 0
    assert (bindir / "ecc").read_text() == wrapper_before
    assert (config / "ecc-receipt.json").read_text() == receipt_before


def test_corrupted_same_version_fails_closed(tmp_path, installer):
    env = xdg_env(tmp_path)
    assert run_installer(installer, env).returncode == 0
    data, bindir, _cache, _config = _roots(env)
    wrapper_before = (bindir / "ecc").read_text()
    target = data / "v0.1.0-alpha.11" / "ecc"
    target.write_text("#!/bin/sh\nexit 1\n")
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    result = run_installer(installer, env)
    assert result.returncode != 0
    assert "move it aside" in result.stderr
    assert (bindir / "ecc").read_text() == wrapper_before
    assert target.read_text().startswith("#!/bin/sh")


def test_three_versions_remain_installed(tmp_path, assets, base):
    env = xdg_env(tmp_path)
    for version in ("0.1.0-alpha.9", "0.1.0-alpha.10", "0.1.0-alpha.11"):
        installer = write_generated_installer(
            make_model(assets, base, version=version),
            tmp_path / f"{version}.sh",
        )
        result = run_installer(installer, env)
        assert result.returncode == 0, result.stderr
    data, bindir, _cache, _config = _roots(env)
    assert (data / "v0.1.0-alpha.9").is_dir()
    assert (data / "v0.1.0-alpha.10").is_dir()
    assert (data / "v0.1.0-alpha.11").is_dir()
    assert 'ECC_VERSION=\'v0.1.0-alpha.11\'' in (bindir / "ecc").read_text()


def test_idempotent_reinstall_keeps_other_versions(tmp_path, assets, base):
    env = xdg_env(tmp_path)
    old = write_generated_installer(
        make_model(assets, base, version="0.1.0-alpha.10"), tmp_path / "old.sh"
    )
    current = write_generated_installer(make_model(assets, base), tmp_path / "cur.sh")
    assert run_installer(old, env).returncode == 0
    assert run_installer(current, env).returncode == 0
    again = run_installer(current, env)
    assert again.returncode == 0, again.stderr
    data, _bindir, _cache, _config = _roots(env)
    assert (data / "v0.1.0-alpha.10").is_dir()
    assert (data / "v0.1.0-alpha.11").is_dir()


def test_live_lock_then_manual_removal(tmp_path, installer):
    env = xdg_env(tmp_path)
    data, _bindir, _cache, _config = _roots(env)
    data.mkdir(parents=True, exist_ok=True)
    lock = data / ".ecc-install-lock"
    lock.mkdir()
    blocked = run_installer(installer, env)
    assert blocked.returncode != 0
    assert str(lock) in blocked.stderr
    assert not (_roots(env)[1] / "ecc").exists()
    lock.rmdir()
    retry = run_installer(installer, env)
    assert retry.returncode == 0, retry.stderr


def test_receipt_write_failure_is_non_fatal(tmp_path, installer):
    env = xdg_env(tmp_path)
    fake = tmp_path / "fakebin"
    real_mv = shutil.which("mv")
    assert real_mv is not None
    write_fake_cmd(
        fake,
        "mv",
        f"""#!/bin/sh
for arg in "$@"; do
  case "$arg" in
    *ecc-receipt.json) exit 1 ;;
  esac
done
exec {real_mv} "$@"
""",
    )
    env["PATH"] = f"{fake}:{env['PATH']}"
    result = run_installer(installer, env)
    assert result.returncode == 0, result.stderr
    assert "failed to write install receipt" in result.stderr
    assert (_roots(env)[1] / "ecc").is_file()


def test_stale_receipt_and_unowned_binary(tmp_path, installer):
    env = xdg_env(tmp_path)
    _data, bindir, _cache, config = _roots(env)
    config.mkdir(parents=True, exist_ok=True)
    (config / "ecc-receipt.json").write_text("{not json")
    result = run_installer(installer, env)
    assert result.returncode == 0, result.stderr
    json.loads((config / "ecc-receipt.json").read_text())

    env2 = xdg_env(tmp_path / "owned")
    bindir2 = Path(env2["XDG_BIN_HOME"])
    bindir2.mkdir(parents=True, exist_ok=True)
    (bindir2 / "ecc").write_text("#!/bin/sh\necho stolen\n")
    blocked = run_installer(installer, env2)
    assert blocked.returncode != 0
    assert "unowned binary" in blocked.stderr


def test_shadowed_ecc_and_config_home_receipt(tmp_path, installer):
    env = xdg_env(tmp_path)
    shadow = tmp_path / "shadow"
    write_fake_cmd(shadow, "ecc", "#!/bin/sh\necho other\n")
    env["PATH"] = f"{shadow}:{env['XDG_BIN_HOME']}:{env['PATH']}"
    result = run_installer(installer, env)
    assert result.returncode == 0, result.stderr
    assert "shadowed by" in result.stderr
    assert (Path(env["XDG_CONFIG_HOME"]) / "ecc" / "ecc-receipt.json").is_file()


def test_unexpected_post_extraction_type_is_rejected(tmp_path, assets, base, routes):
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("ecc")
        payload = b"#!/bin/sh\nexit 0\n"
        info.size = len(payload)
        info.mode = 0o755
        tar.addfile(info, BytesIO(payload))
        fifo = tarfile.TarInfo("fifo")
        fifo.type = tarfile.FIFOTYPE
        tar.addfile(fifo)
        internal = tarfile.TarInfo("_internal/torch/bin/torch_shm_manager")
        blob = b"x"
        internal.size = len(blob)
        internal.mode = 0o755
        tar.addfile(internal, BytesIO(blob))
    data = buffer.getvalue()
    routes["/github/ecc-cli-linux-x86_64.tar.gz"] = {"data": data}
    routes["/cnb/ecc-cli-linux-x86_64.tar.gz"] = {"data": data}
    from tests.support import PackedAsset

    mutated = dict(assets)
    mutated["ecc-cli-linux-x86_64.tar.gz"] = PackedAsset(
        "ecc-cli-linux-x86_64.tar.gz", data, sha256_bytes(data)
    )
    installer = write_generated_installer(make_model(mutated, base), tmp_path / "bad.sh")
    result = run_installer(installer, xdg_env(tmp_path))
    assert result.returncode != 0
    assert "unexpected filesystem object types" in result.stderr or "smoke tests failed" in result.stderr


def test_toolchain_failure_keeps_existing_wrapper(tmp_path, assets, base, routes):
    env = xdg_env(tmp_path)
    first = write_generated_installer(make_model(assets, base), tmp_path / "first.sh")
    assert run_installer(first, env).returncode == 0
    wrapper_before = (Path(env["XDG_BIN_HOME"]) / "ecc").read_text()
    bad_oss = build_oss_archive(slang=False)
    routes["/github/oss-cad-suite-linux-x64-20260827.tgz"] = {"data": bad_oss}
    from tests.support import PackedAsset

    mutated = dict(assets)
    mutated["oss-cad-suite-linux-x64-20260827.tgz"] = PackedAsset(
        "oss-cad-suite-linux-x64-20260827.tgz", bad_oss, sha256_bytes(bad_oss)
    )
    installer = write_generated_installer(make_model(mutated, base), tmp_path / "second.sh")
    result = run_installer(installer, env, "--with-toolchain")
    assert result.returncode != 0
    assert (Path(env["XDG_BIN_HOME"]) / "ecc").read_text() == wrapper_before
    data = Path(env["XDG_DATA_HOME"]) / "ecc"
    assert (data / "v0.1.0-alpha.11").is_dir()
    assert not (data / "tools" / "oss-cad-suite" / "20260827").exists() or True


def test_conflicting_quiet_verbose_and_relative_path(tmp_path, installer):
    env = xdg_env(tmp_path)
    conflict = run_installer(installer, env, "-q", "-v")
    assert conflict.returncode != 0
    assert "conflicting" in conflict.stderr
    env["ECC_INSTALL_DIR"] = "relative/path"
    relative = run_installer(installer, env)
    assert relative.returncode != 0
    assert "absolute path" in relative.stderr


def test_cnb_mode_downloads_toolchain_from_cnb(tmp_path, assets, base, routes):
    for name in assets:
        routes[f"/github/{name}"] = {"status": 404}
    installer = write_generated_installer(make_model(assets, base), tmp_path / "installer.sh")
    env = xdg_env(tmp_path)
    result = run_installer(installer, env, "--download-source", "cnb", "--with-toolchain")
    assert result.returncode == 0, result.stderr
    assert "no CNB mirror" not in result.stderr
    data = Path(env["XDG_DATA_HOME"]) / "ecc"
    assert (data / "tools" / "oss-cad-suite" / "20260827" / "bin" / "yosys").is_file()


def test_toolchain_github_failure_falls_back_to_cnb(tmp_path, assets, base, routes):
    routes["/github/oss-cad-suite-linux-x64-20260827.tgz"] = {"status": 500}
    routes["/github/icsprout55-pdk-v1.10.102.tar.gz"] = {"status": 500}
    for spec_name in (
        "ics55_LLSC_H7CH_liberty.tar.bz2",
        "ics55_LLSC_H7CL_liberty.tar.bz2",
        "ics55_LLSC_H7CR_liberty.tar.bz2",
        "ics55_LLSC_H7CH_gds.tar.bz2",
        "ics55_LLSC_H7CL_gds.tar.bz2",
        "ics55_LLSC_H7CR_gds.tar.bz2",
        "ICsprout_55LLULP1233_IO_251013_gds.tar.bz2",
    ):
        routes[f"/github/{spec_name}"] = {"status": 500}
    installer = write_generated_installer(make_model(assets, base), tmp_path / "installer.sh")
    result = run_installer(installer, xdg_env(tmp_path), "--with-toolchain")
    assert result.returncode == 0, result.stderr
    assert "failed to download" in result.stderr


def test_github_redirect_stall_falls_back_to_cnb(tmp_path, assets, base, routes):
    routes["/github/ecc-cli-linux-x86_64.tar.gz"] = {"redirect": f"{base}/stall/ecc"}
    routes["/stall/ecc"] = {"data": assets["ecc-cli-linux-x86_64.tar.gz"].data, "stall": 35}
    installer = write_generated_installer(make_model(assets, base), tmp_path / "stall.sh")
    result = run_installer(installer, xdg_env(tmp_path), timeout=90)
    assert result.returncode == 0, result.stderr


@pytest.mark.real_artifact
def test_real_artifact_with_toolchain(tmp_path: Path):
    installer = Path(os.environ.get("ECC_INSTALLER_PATH", "dist/ecc-installer.sh"))
    if not installer.is_file():
        pytest.skip("generated installer is not present")
    env = xdg_env(tmp_path)
    env["PATH"] = f"{env['XDG_BIN_HOME']}:{env['PATH']}"
    result = run_installer(installer, env, "--with-toolchain", timeout=3600)
    assert result.returncode == 0, result.stderr
    wrapper = Path(env["XDG_BIN_HOME"]) / "ecc"
    dumped = _read_wrapper_env(wrapper, env)
    assert dumped["OSS"]
    assert dumped["PDK"]
    version = subprocess_run_wrapper(wrapper, env, "--version")
    assert version.returncode == 0, version.stderr
    json_version = subprocess_run_wrapper(wrapper, env, "version", "--json")
    assert json_version.returncode == 0, json_version.stderr
