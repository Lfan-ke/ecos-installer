from ecos_release.semver import InvalidVersion, parse, parse_tag

import pytest


def test_parse_rejects_invalid_versions():
    with pytest.raises(InvalidVersion):
        parse("v0.1.0")
    with pytest.raises(InvalidVersion):
        parse("01.0.0")
    with pytest.raises(InvalidVersion):
        parse_tag("0.1.0-alpha.11")


def test_prerelease_ordering():
    versions = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    ]
    parsed = [parse(item) for item in versions]
    assert parsed == sorted(parsed)
    assert parse("0.1.0-alpha.10") < parse("0.1.0-alpha.11")
    assert parse("0.1.0-alpha.11") < parse("0.1.0")
