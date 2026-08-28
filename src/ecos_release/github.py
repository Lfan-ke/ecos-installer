"""GitHub Release Asset API helpers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ecos_release.model import ECC_ASSET_NAME, InvalidReleaseModel, parse_digest

GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class GithubAsset:
    name: str
    url: str
    size: int
    sha256: str


def fetch_release(repo: str, tag: str, *, token: str | None = None) -> dict[str, Any]:
    url = f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}"
    request = urllib.request.Request(
        url,
        headers=_headers(token),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise InvalidReleaseModel(
            f"GitHub release {repo}@{tag} is unavailable: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise InvalidReleaseModel(f"GitHub release {repo}@{tag} is unreachable: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidReleaseModel(f"unexpected GitHub release payload for {repo}@{tag}")
    return payload


def select_ecc_asset(release: dict[str, Any], *, name: str = ECC_ASSET_NAME) -> GithubAsset:
    assets = release.get("assets") or []
    matches = [asset for asset in assets if asset.get("name") == name]
    if not matches:
        raise InvalidReleaseModel(f"GitHub release is missing asset {name}")
    if len(matches) != 1:
        raise InvalidReleaseModel(f"GitHub release has multiple assets named {name}")
    asset = matches[0]
    digest = asset.get("digest")
    if not isinstance(digest, str):
        raise InvalidReleaseModel(f"GitHub asset {name} is missing a digest")
    url = asset.get("browser_download_url")
    size = asset.get("size")
    if not isinstance(url, str) or not url:
        raise InvalidReleaseModel(f"GitHub asset {name} is missing a download URL")
    if not isinstance(size, int):
        raise InvalidReleaseModel(f"GitHub asset {name} is missing a size")
    return GithubAsset(name=name, url=url, size=size, sha256=parse_digest(digest))


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ecos-release",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resolved = token if token is not None else os.environ.get("GITHUB_TOKEN")
    if resolved:
        headers["Authorization"] = f"Bearer {resolved}"
    return headers
