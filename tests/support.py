"""Helpers for building fake release archives and serving them locally."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tarfile
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from ecos_release.generator import write_installer
from ecos_release.model import Asset, ReleaseModel

CELL_LEFS = (
    "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR/lef/ics55_LLSC_H7CR_ecos.lef",
    "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL/lef/ics55_LLSC_H7CL_ecos.lef",
)
TECH_LEF = "prtech/techLEF/N551P6M_ecos.lef"
LIBERTY_SPECS = (
    (
        "ics55_LLSC_H7CH_liberty.tar.bz2",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CH/liberty",
        "h7ch.lib",
    ),
    (
        "ics55_LLSC_H7CL_liberty.tar.bz2",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL/liberty",
        "h7cl.lib",
    ),
    (
        "ics55_LLSC_H7CR_liberty.tar.bz2",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR/liberty",
        "h7cr.lib",
    ),
)
GDS_SPECS = (
    (
        "ics55_LLSC_H7CH_gds.tar.bz2",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CH/gds",
        "h7ch.gds",
    ),
    (
        "ics55_LLSC_H7CL_gds.tar.bz2",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CL/gds",
        "h7cl.gds",
    ),
    (
        "ics55_LLSC_H7CR_gds.tar.bz2",
        "IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_H7CR/gds",
        "h7cr.gds",
    ),
    (
        "ICsprout_55LLULP1233_IO_251013_gds.tar.bz2",
        "IP/IO/ICsprout_55LLULP1233_IO_251013/gds",
        "io.gds",
    ),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pack_tar(members: dict[str, bytes | None], *, compression: str) -> bytes:
    buffer = BytesIO()
    mode = {"gz": "w:gz", "bz2": "w:bz2", "none": "w"}[compression]
    with tarfile.open(fileobj=buffer, mode=mode) as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            if content is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
                continue
            payload = content
            info.size = len(payload)
            info.mode = 0o755 if _executable_member(name, payload) else 0o644
            tar.addfile(info, BytesIO(payload))
    return buffer.getvalue()


def _executable_member(name: str, payload: bytes) -> bool:
    base = PurePosixPath(name).name
    return payload.startswith(b"#!") or base in {"ecc", "yosys", "torch_shm_manager"}


def ecc_script(version: str, *, fail: bool = False) -> bytes:
    status = "1" if fail else "0"
    return f"""#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "ecc {version}"
  exit {status}
fi
if [ "$1" = "version" ] && [ "${{2:-}}" = "--json" ]; then
  echo '{{"schema_version":1,"runtime":"ECC CLI","ecc":"{version}"}}'
  exit {status}
fi
if [ "$1" = "dump-env" ]; then
  printf 'OSS=%s\\n' "${{CHIPCOMPILER_OSS_CAD_DIR-}}"
  printf 'PDK=%s\\n' "${{CHIPCOMPILER_ICS55_PDK_ROOT-}}"
  printf 'PATH=%s\\n' "$PATH"
  printf 'YOSYS_PLUGINPATH=%s\\n' "${{YOSYS_PLUGINPATH-}}"
  printf 'YOSYS_DATDIR=%s\\n' "${{YOSYS_DATDIR-}}"
  exit 0
fi
exit {status}
""".encode()

def yosys_script(*, slang: bool = True) -> bytes:
    if slang:
        body = """
case "$cmd" in
  "help read_slang") echo "read_slang -- read SystemVerilog"; exit 0 ;;
  "plugin -i slang") exit 0 ;;
esac
exit 1
"""
    else:
        body = """
case "$cmd" in
  "help read_slang") echo "No such command: read_slang"; exit 0 ;;
  "plugin -i slang") exit 1 ;;
esac
exit 1
"""
    return f"""#!/bin/sh
cmd=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) echo "Yosys 0.67 (test)"; exit 0 ;;
    -Q|-T) ;;
    -p) cmd="$2"; shift ;;
  esac
  shift
done
{body}
""".encode()


def build_ecc_archive(version: str = "0.1.0-alpha.11", *, fail: bool = False) -> bytes:
    return pack_tar(
        {
            "ecc": ecc_script(version, fail=fail),
            "_internal/torch/bin/torch_shm_manager": b"shm\n",
        },
        compression="gz",
    )


def build_oss_archive(*, slang: bool = True) -> bytes:
    return pack_tar(
        {
            "oss-cad-suite/bin/yosys": yosys_script(slang=slang),
            "oss-cad-suite/share/yosys/plugins/.keep": b"",
        },
        compression="gz",
    )


def build_pdk_base_archive() -> bytes:
    members: dict[str, bytes | None] = {
        f"icsprout55-pdk/{TECH_LEF}": b"VERSION 5.8 ;\n",
    }
    for path in CELL_LEFS:
        members[f"icsprout55-pdk/{path}"] = b"MACRO TEST ;\nEND TEST\n"
    return pack_tar(members, compression="gz")


def build_named_bz2(filename: str, dest_file: str) -> bytes:
    return pack_tar({dest_file: b"contents of %s\n" % dest_file.encode()}, compression="bz2")


@dataclass
class PackedAsset:
    name: str
    data: bytes
    sha256: str
    dest: str | None = None
    kind: str = "archive"


def build_release_assets(*, version: str = "0.1.0-alpha.11") -> dict[str, PackedAsset]:
    assets: dict[str, PackedAsset] = {}
    ecc = build_ecc_archive(version)
    assets["ecc-cli-linux-x86_64.tar.gz"] = PackedAsset(
        "ecc-cli-linux-x86_64.tar.gz", ecc, sha256_bytes(ecc)
    )
    oss = build_oss_archive()
    assets["oss-cad-suite-linux-x64-20260827.tgz"] = PackedAsset(
        "oss-cad-suite-linux-x64-20260827.tgz", oss, sha256_bytes(oss)
    )
    pdk_base = build_pdk_base_archive()
    assets["icsprout55-pdk-v1.10.102.tar.gz"] = PackedAsset(
        "icsprout55-pdk-v1.10.102.tar.gz", pdk_base, sha256_bytes(pdk_base)
    )
    for name, dest, filename in LIBERTY_SPECS:
        data = build_named_bz2(name, filename)
        assets[name] = PackedAsset(name, data, sha256_bytes(data), dest=dest, kind="liberty")
    for name, dest, filename in GDS_SPECS:
        data = build_named_bz2(name, filename)
        assets[name] = PackedAsset(name, data, sha256_bytes(data), dest=dest, kind="gds")
    return assets


def liberty_paths() -> tuple[str, ...]:
    return tuple(f"{dest}/{filename}" for _, dest, filename in LIBERTY_SPECS)


class AssetServer(ThreadingHTTPServer):
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        super().__init__(("127.0.0.1", 0), _AssetHandler)
        self.routes = routes


class _AssetHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        route = self.server.routes.get(self.path)  # type: ignore[attr-defined]
        if route is None:
            self.send_error(404)
            return
        if "redirect" in route:
            self.send_response(302)
            self.send_header("Location", route["redirect"])
            self.end_headers()
            return
        status = int(route.get("status", 200))
        if status != 200:
            self.send_error(status)
            return
        data: bytes = route.get("data", b"")
        stall = float(route.get("stall", 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if stall:
            self.wfile.write(data[:64] if data else b"x")
            self.wfile.flush()
            time.sleep(stall)
            return
        self.wfile.write(data)


def start_server(routes: dict[str, dict[str, Any]]) -> AssetServer:
    server = AssetServer(routes)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def server_base(server: AssetServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}"


def default_routes(assets: dict[str, PackedAsset]) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    for asset in assets.values():
        payload = {"data": asset.data}
        routes[f"/github/{asset.name}"] = payload
        routes[f"/cnb/{asset.name}"] = payload
    return routes


def make_model(
    assets: dict[str, PackedAsset],
    base: str,
    *,
    version: str = "0.1.0-alpha.11",
    ecc_github: str | None = None,
    ecc_cnb: str | None = None,
) -> ReleaseModel:
    ecc = assets["ecc-cli-linux-x86_64.tar.gz"]
    oss = assets["oss-cad-suite-linux-x64-20260827.tgz"]
    pdk_base = assets["icsprout55-pdk-v1.10.102.tar.gz"]
    supplemental = []
    for spec in (*LIBERTY_SPECS, *GDS_SPECS):
        packed = assets[spec[0]]
        supplemental.append(
            Asset(
                name=packed.name,
                url=f"{base}/github/{packed.name}",
                sha256=packed.sha256,
                dest=packed.dest,
                kind=packed.kind,
                cnb_url=f"{base}/cnb/{packed.name}",
            )
        )
    return ReleaseModel(
        ecc_version=version,
        ecc_tag=f"v{version}",
        ecc=Asset(
            name=ecc.name,
            url=ecc_github or f"{base}/github/{ecc.name}",
            sha256=ecc.sha256,
            size=len(ecc.data),
        ),
        ecc_cnb_url=ecc_cnb or f"{base}/cnb/{ecc.name}",
        oss_cad_version="20260827",
        oss_cad=Asset(
            name=oss.name,
            url=f"{base}/github/{oss.name}",
            sha256=oss.sha256,
            size=len(oss.data),
            cnb_url=f"{base}/cnb/{oss.name}",
        ),
        pdk_version="v1.10.102",
        pdk_base=Asset(
            name=pdk_base.name,
            url=f"{base}/github/{pdk_base.name}",
            sha256=pdk_base.sha256,
            size=len(pdk_base.data),
            cnb_url=f"{base}/cnb/{pdk_base.name}",
        ),
        pdk_supplemental=tuple(supplemental),
        pdk_liberty_files=liberty_paths(),
        pdk_tech_lef=TECH_LEF,
        pdk_cell_lefs=CELL_LEFS,
    )


def xdg_env(root: Path, *, extra_path: str = "") -> dict[str, str]:
    home = root / "home"
    data = root / "data"
    bindir = root / "bin"
    cache = root / "cache"
    config = root / "config"
    for path in (home, data, bindir, cache, config):
        path.mkdir(parents=True, exist_ok=True)
    path_value = os.environ.get("PATH", "/usr/bin:/bin")
    if extra_path:
        path_value = f"{extra_path}:{path_value}"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_DATA_HOME": str(data),
            "XDG_BIN_HOME": str(bindir),
            "XDG_CACHE_HOME": str(cache),
            "XDG_CONFIG_HOME": str(config),
            "PATH": path_value,
            "SHELL": env.get("SHELL", "/bin/sh"),
        }
    )
    env.pop("ECC_WITH_TOOLCHAIN", None)
    env.pop("ECC_DOWNLOAD_SOURCE", None)
    env.pop("ECC_INSTALL_DIR", None)
    return env


def write_fake_cmd(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def run_installer(
    installer: Path,
    env: dict[str, str],
    *args: str,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(installer), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def write_generated_installer(model: ReleaseModel, path: Path) -> Path:
    return write_installer(model, path)
