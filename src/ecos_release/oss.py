"""Aliyun OSS helpers for versioned installer publication."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import urllib.error
import urllib.request
from email.utils import formatdate

from ecos_release.publish import PublishError


class OssStore:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint: str,
        access_key_id: str,
        access_key_secret: str,
        public_base: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.public_base = (public_base or f"https://{bucket}.{endpoint}").rstrip("/")

    def object_url(self, key: str) -> str:
        return f"https://{self.bucket}.{self.endpoint}/{key}"

    def public_url(self, key: str) -> str:
        return f"{self.public_base}/{key}"

    def get(self, key: str) -> bytes | None:
        request = self._signed_request("GET", key)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise PublishError(f"OSS GET {key} failed: HTTP {exc.code}") from exc

    def get_anonymous(self, key: str) -> tuple[bytes, dict[str, str]]:
        request = urllib.request.Request(self.public_url(key), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                headers = {k: v for k, v in response.headers.items()}
                return response.read(), headers
        except urllib.error.HTTPError as exc:
            raise PublishError(f"anonymous OSS GET {key} failed: HTTP {exc.code}") from exc

    def put(self, key: str, data: bytes, headers: dict[str, str]) -> None:
        self._put(key, data, headers, forbid_overwrite=False)

    def put_if_absent_or_same(
        self, key: str, data: bytes, headers: dict[str, str]
    ) -> None:
        try:
            self._put(key, data, headers, forbid_overwrite=True)
            return
        except PublishError as exc:
            if "HTTP 409" not in str(exc) and "HTTP 403" not in str(exc):
                raise
        existing = self.get(key)
        if existing is None:
            raise PublishError(f"OSS object {key} exists but could not be read back")
        if existing != data:
            raise PublishError(f"refusing to overwrite {key} with different bytes")

    def _put(
        self,
        key: str,
        data: bytes,
        headers: dict[str, str],
        *,
        forbid_overwrite: bool,
    ) -> None:
        extra = dict(headers)
        if forbid_overwrite:
            extra["x-oss-forbid-overwrite"] = "true"
        request = self._signed_request("PUT", key, data=data, extra_headers=extra)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            raise PublishError(f"OSS PUT {key} failed: HTTP {exc.code}") from exc

    def _signed_request(
        self,
        method: str,
        key: str,
        *,
        data: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> urllib.request.Request:
        date = formatdate(usegmt=True)
        headers = {"Date": date, "Host": f"{self.bucket}.{self.endpoint}"}
        content_type = ""
        if extra_headers:
            headers.update(extra_headers)
            content_type = extra_headers.get("Content-Type", "")
        canonical_oss = ""
        oss_headers = {k.lower(): v for k, v in headers.items() if k.lower().startswith("x-oss-")}
        if oss_headers:
            canonical_oss = (
                "".join(f"{name}:{oss_headers[name]}\n" for name in sorted(oss_headers))
            )
        canonical = f"{method}\n\n{content_type}\n{date}\n{canonical_oss}/{self.bucket}/{key}"
        signature = base64.b64encode(
            hmac.new(
                self.access_key_secret.encode("utf-8"),
                canonical.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")
        headers["Authorization"] = f"OSS {self.access_key_id}:{signature}"
        return urllib.request.Request(
            self.object_url(key),
            data=data,
            headers=headers,
            method=method,
        )


def store_from_env() -> OssStore:
    bucket = os.environ.get("OSS_BUCKET", "ecc-install-script")
    endpoint = os.environ.get("OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")
    access_key_id = os.environ.get("OSS_ACCESS_KEY_ID", "")
    access_key_secret = os.environ.get("OSS_ACCESS_KEY_SECRET", "")
    if not access_key_id or not access_key_secret:
        raise PublishError("OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET are required")
    return OssStore(
        bucket=bucket,
        endpoint=endpoint,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        public_base=os.environ.get(
            "OSS_PUBLIC_BASE",
            "https://ecc-install-script.oss-cn-beijing.aliyuncs.com",
        ),
    )
