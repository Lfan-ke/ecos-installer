import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from ecos_release.archive import UnsafeArchive, liberty_destinations, validate_archive
from tests.support import pack_tar


def _write(tmp_path: Path, members: dict[str, bytes | None], name: str, compression: str) -> Path:
    path = tmp_path / name
    path.write_bytes(pack_tar(members, compression=compression))
    return path


def test_accepts_regular_files_and_collects_liberty(tmp_path: Path):
    path = _write(tmp_path, {"lib/cell.lib": b"library() {}\n", "readme": b"ok\n"}, "ok.tar.gz", "gz")
    inventory = validate_archive(path, require_liberty=True)
    assert inventory.liberty_files == ("lib/cell.lib",)
    assert liberty_destinations("IP/liberty", inventory.liberty_files) == (
        "IP/liberty/lib/cell.lib",
    )


@pytest.mark.parametrize("compression,name", [("gz", "bad.tar.gz"), ("bz2", "bad.tar.bz2")])
def test_rejects_traversal_and_empty_liberty(tmp_path: Path, compression: str, name: str):
    path = tmp_path / name
    buffer = BytesIO()
    mode = "w:gz" if compression == "gz" else "w:bz2"
    with tarfile.open(fileobj=buffer, mode=mode) as tar:
        info = tarfile.TarInfo("keep/../../outside")
        data = b"nope\n"
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    path.write_bytes(buffer.getvalue())
    with pytest.raises(UnsafeArchive):
        validate_archive(path)
    empty = _write(tmp_path, {"readme.txt": b"no liberty\n"}, f"empty-{name}", compression)
    with pytest.raises(UnsafeArchive):
        validate_archive(empty, require_liberty=True)

def test_rejects_absolute_and_control_paths(tmp_path: Path):
    absolute = tmp_path / "abs.tar.gz"
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("/tmp/evil")
        data = b"x"
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    absolute.write_bytes(buffer.getvalue())
    with pytest.raises(UnsafeArchive):
        validate_archive(absolute)

    control = tmp_path / "ctrl.tar.gz"
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("bad\nname")
        data = b"x"
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    control.write_bytes(buffer.getvalue())
    with pytest.raises(UnsafeArchive):
        validate_archive(control)


def test_rejects_escaping_symlink_and_fifo(tmp_path: Path):
    link = tmp_path / "link.tar.gz"
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../outside"
        tar.addfile(info)
    link.write_bytes(buffer.getvalue())
    with pytest.raises(UnsafeArchive):
        validate_archive(link)

    fifo = tmp_path / "fifo.tar.gz"
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("pipe")
        info.type = tarfile.FIFOTYPE
        tar.addfile(info)
    fifo.write_bytes(buffer.getvalue())
    with pytest.raises(UnsafeArchive):
        validate_archive(fifo)
