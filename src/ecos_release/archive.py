"""Structured tar archive validation for installer publication."""

from __future__ import annotations

import posixpath
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALLOWED_TYPES = {
    tarfile.REGTYPE,
    tarfile.AREGTYPE,
    tarfile.DIRTYPE,
    tarfile.SYMTYPE,
    tarfile.LNKTYPE,
}


class UnsafeArchive(ValueError):
    """Raised when an archive member violates the publication safety policy."""


@dataclass(frozen=True)
class ArchiveInventory:
    members: tuple[str, ...]
    liberty_files: tuple[str, ...]


def validate_archive(
    path: Path | str,
    *,
    require_liberty: bool = False,
) -> ArchiveInventory:
    archive_path = Path(path)
    members: list[str] = []
    liberty: list[str] = []
    with tarfile.open(archive_path, mode="r:*") as tar:
        for info in tar.getmembers():
            _validate_member(info)
            members.append(info.name)
            if _is_liberty_member(info):
                liberty.append(_normalized_member_path(info.name))
    if require_liberty and not liberty:
        raise UnsafeArchive(f"{archive_path.name} contains no .lib members")
    return ArchiveInventory(members=tuple(members), liberty_files=tuple(sorted(liberty)))


def liberty_destinations(dest: str, liberty_members: Iterable[str]) -> tuple[str, ...]:
    destinations = []
    dest_root = _normalized_member_path(dest)
    for member in liberty_members:
        joined = posixpath.normpath(posixpath.join(dest_root, member))
        if joined == dest_root or not _is_within(dest_root, joined):
            raise UnsafeArchive(f"Liberty member {member!r} escapes destination {dest!r}")
        destinations.append(joined)
    return tuple(sorted(destinations))


def _validate_member(info: tarfile.TarInfo) -> None:
    name = info.name
    if name is None or name == "":
        raise UnsafeArchive("empty member path")
    if _has_control(name):
        raise UnsafeArchive(f"control character in member path: {name!r}")
    normalized = _normalized_member_path(name)
    if normalized.startswith("/") or PurePosixPath(name).is_absolute():
        raise UnsafeArchive(f"absolute member path: {name!r}")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise UnsafeArchive(f"parent traversal in member path: {name!r}")
    if info.type not in ALLOWED_TYPES:
        raise UnsafeArchive(f"unsupported member type {info.type!r} for {name}")
    if info.issym() or info.islnk():
        target = info.linkname or ""
        if not target:
            raise UnsafeArchive(f"empty link target for {name}")
        if _has_control(target):
            raise UnsafeArchive(f"control character in link target: {target!r}")
        if PurePosixPath(target).is_absolute() or target.startswith("/"):
            raise UnsafeArchive(f"absolute link target for {name}: {target!r}")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(normalized), target))
        if any(part == ".." for part in PurePosixPath(resolved).parts) or resolved.startswith("/"):
            raise UnsafeArchive(f"link target for {name} escapes staging root: {target!r}")


def _is_liberty_member(info: tarfile.TarInfo) -> bool:
    if not info.isfile():
        return False
    return _normalized_member_path(info.name).endswith(".lib")


def _normalized_member_path(name: str) -> str:
    stripped = name.lstrip("./")
    if stripped == "":
        raise UnsafeArchive(f"empty member path: {name!r}")
    return posixpath.normpath(stripped)


def _is_within(root: str, candidate: str) -> bool:
    root_n = posixpath.normpath(root)
    cand_n = posixpath.normpath(candidate)
    return cand_n == root_n or cand_n.startswith(root_n + "/")


def _has_control(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
