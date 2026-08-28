"""Semantic Versioning 2.0.0 parsing and precedence."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER_RE = re.compile(
    r"""
    ^
    (?P<major>0|[1-9]\d*)
    \.
    (?P<minor>0|[1-9]\d*)
    \.
    (?P<patch>0|[1-9]\d*)
    (?:-(?P<prerelease>(?:0|[1-9]\d*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)
        (?:\.(?:0|[1-9]\d*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?
    (?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?
    $
    """,
    re.VERBOSE,
)


class InvalidVersion(ValueError):
    """Raised when a string is not a valid SemVer 2.0.0 version."""


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: str = ""

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            core += "-" + ".".join(self.prerelease)
        if self.build:
            core += "+" + self.build
        return core

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return _compare(self, other) < 0

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return _compare(self, other) <= 0

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return _compare(self, other) > 0

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return _compare(self, other) >= 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return _compare(self, other) == 0


def parse(value: str) -> Version:
    match = _SEMVER_RE.match(value)
    if match is None:
        raise InvalidVersion(f"invalid SemVer 2.0.0 version: {value!r}")
    prerelease = match.group("prerelease")
    build = match.group("build") or ""
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=tuple(prerelease.split(".")) if prerelease else (),
        build=build,
    )


def parse_tag(tag: str) -> Version:
    if not tag.startswith("v"):
        raise InvalidVersion(f"ECC tag must be v<version>, got {tag!r}")
    return parse(tag[1:])


def _ident_key(ident: str) -> tuple[int, int | str]:
    if ident.isdigit():
        return (0, int(ident))
    return (1, ident)


def _compare(left: Version, right: Version) -> int:
    for a, b in (
        (left.major, right.major),
        (left.minor, right.minor),
        (left.patch, right.patch),
    ):
        if a != b:
            return -1 if a < b else 1
    if not left.prerelease and not right.prerelease:
        return 0
    if not left.prerelease:
        return 1
    if not right.prerelease:
        return -1
    for l_id, r_id in zip(left.prerelease, right.prerelease, strict=False):
        if l_id == r_id:
            continue
        l_key = _ident_key(l_id)
        r_key = _ident_key(r_id)
        if l_key < r_key:
            return -1
        if l_key > r_key:
            return 1
    if len(left.prerelease) == len(right.prerelease):
        return 0
    return -1 if len(left.prerelease) < len(right.prerelease) else 1
