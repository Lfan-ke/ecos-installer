from ecos_release.generator import generate_installer
from ecos_release.publish import (
    LATEST_HEADERS,
    VERSIONED_HEADERS,
    MemoryStore,
    PublishError,
    latest_key,
    publish_installer,
    versioned_key,
)

import pytest

from tests.support import build_release_assets, make_model, start_server, default_routes, server_base


def _installer(version: str) -> bytes:
    assets = build_release_assets(version=version)
    server = start_server(default_routes(assets))
    try:
        model = make_model(assets, server_base(server), version=version)
        return generate_installer(model).encode("utf-8")
    finally:
        server.shutdown()


def test_idempotent_publish_and_header_assignment():
    store = MemoryStore(objects={})
    installer = _installer("0.1.0-alpha.11")
    first = publish_installer(store, tag="v0.1.0-alpha.11", installer=installer)
    second = publish_installer(store, tag="v0.1.0-alpha.11", installer=installer)
    assert first["latest_updated"] == "true"
    assert second["versioned"] == versioned_key("v0.1.0-alpha.11")
    assert store.get(latest_key()) == installer
    assert store.headers(versioned_key("v0.1.0-alpha.11")) == VERSIONED_HEADERS
    assert store.headers(latest_key()) == LATEST_HEADERS


def test_rejects_different_bytes_at_versioned_path():
    store = MemoryStore(objects={})
    installer = _installer("0.1.0-alpha.11")
    publish_installer(store, tag="v0.1.0-alpha.11", installer=installer)
    with pytest.raises(PublishError):
        publish_installer(store, tag="v0.1.0-alpha.11", installer=installer + b"\n")


def test_older_semver_does_not_downgrade_latest():
    store = MemoryStore(objects={})
    newer = _installer("0.1.0-alpha.11")
    older = _installer("0.1.0-alpha.10")
    publish_installer(store, tag="v0.1.0-alpha.11", installer=newer)
    result = publish_installer(store, tag="v0.1.0-alpha.10", installer=older)
    assert result["latest_updated"] == "false"
    assert store.get(latest_key()) == newer
    assert store.get(versioned_key("v0.1.0-alpha.10")) == older


def test_malformed_latest_fails_closed():
    store = MemoryStore(objects={})
    store.put(latest_key(), b"not an installer", LATEST_HEADERS)
    with pytest.raises(PublishError):
        publish_installer(store, tag="v0.1.0-alpha.11", installer=_installer("0.1.0-alpha.11"))
