"""Small, synchronous service used to check the latest GitHub release.

The service deliberately has no Qt dependency.  Callers can therefore run it
from their own worker thread and inject a deterministic fetcher in tests.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from pixopdf.config import APP_NAME, PROJECT_URL, UPDATE_CHECK_URL, VERSION

MAX_UPDATE_PAYLOAD_BYTES = 1024 * 1024
DEFAULT_UPDATE_TIMEOUT_SECONDS = 8.0

UpdateFetcher = Callable[[str, float, int], bytes]


class UpdateStatus(StrEnum):
    """Possible states for a successful update check."""

    AVAILABLE = "available"
    CURRENT = "current"


class UpdateErrorCode(StrEnum):
    """Machine-readable update failure categories."""

    INSECURE_URL = "insecure_url"
    NETWORK = "network"
    HTTP = "http"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    INVALID_RESPONSE = "invalid_response"
    INVALID_VERSION = "invalid_version"


class UpdateCheckError(RuntimeError):
    """Structured error raised when an update check cannot be completed."""

    def __init__(
        self,
        code: UpdateErrorCode,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Normalized details returned by a successful update check."""

    status: UpdateStatus
    current_version: str
    latest_version: str
    release_url: str
    release_notes: str


class _PayloadTooLargeError(RuntimeError):
    pass


def _default_fetcher(url: str, timeout: float, max_bytes: int) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            if declared_size > max_bytes:
                raise _PayloadTooLargeError

        payload = cast(bytes, response.read(max_bytes + 1))
        if len(payload) > max_bytes:
            raise _PayloadTooLargeError
        return payload


def _is_safe_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


class UpdateService:
    """Retrieve and compare the latest published release version."""

    def __init__(
        self,
        *,
        update_url: str = UPDATE_CHECK_URL,
        project_url: str = PROJECT_URL,
        fetcher: UpdateFetcher | None = None,
        timeout: float = DEFAULT_UPDATE_TIMEOUT_SECONDS,
        max_payload_bytes: int = MAX_UPDATE_PAYLOAD_BYTES,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be greater than zero")

        self._update_url = update_url
        self._project_url = project_url
        self._fetcher = fetcher or _default_fetcher
        self._timeout = timeout
        self._max_payload_bytes = max_payload_bytes

    def check(self, current_version: str = VERSION) -> UpdateResult:
        """Return whether ``current_version`` is current or has an update."""
        if not _is_safe_https_url(self._update_url):
            raise UpdateCheckError(
                UpdateErrorCode.INSECURE_URL,
                "The update endpoint must use HTTPS.",
            )

        try:
            raw_payload = self._fetcher(
                self._update_url,
                self._timeout,
                self._max_payload_bytes,
            )
        except _PayloadTooLargeError as error:
            raise UpdateCheckError(
                UpdateErrorCode.PAYLOAD_TOO_LARGE,
                "The update response exceeds the allowed size.",
                cause=error,
            ) from error
        except HTTPError as error:
            raise UpdateCheckError(
                UpdateErrorCode.HTTP,
                f"The update server returned HTTP {error.code}.",
                cause=error,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise UpdateCheckError(
                UpdateErrorCode.NETWORK,
                "The update server could not be reached.",
                cause=error,
            ) from error
        except Exception as error:
            raise UpdateCheckError(
                UpdateErrorCode.NETWORK,
                "The update request failed.",
                cause=error,
            ) from error

        if not isinstance(raw_payload, bytes):
            raise UpdateCheckError(
                UpdateErrorCode.INVALID_RESPONSE,
                "The update response is not binary data.",
            )
        if len(raw_payload) > self._max_payload_bytes:
            raise UpdateCheckError(
                UpdateErrorCode.PAYLOAD_TOO_LARGE,
                "The update response exceeds the allowed size.",
            )

        payload = self._decode_payload(raw_payload)
        current = self._parse_version(current_version, source="installed")
        latest = self._parse_version(payload["tag_name"], source="release")
        release_url = self._release_url(payload.get("html_url"))
        release_notes = payload.get("body")
        if not isinstance(release_notes, str):
            release_notes = ""

        return UpdateResult(
            status=(UpdateStatus.AVAILABLE if latest > current else UpdateStatus.CURRENT),
            current_version=str(current),
            latest_version=str(latest),
            release_url=release_url,
            release_notes=release_notes,
        )

    @staticmethod
    def _decode_payload(raw_payload: bytes) -> dict[str, object]:
        try:
            decoded: object = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UpdateCheckError(
                UpdateErrorCode.INVALID_RESPONSE,
                "The update server returned invalid JSON.",
                cause=error,
            ) from error

        if not isinstance(decoded, dict):
            raise UpdateCheckError(
                UpdateErrorCode.INVALID_RESPONSE,
                "The update response must be a JSON object.",
            )
        payload = dict(decoded)
        tag_name = payload.get("tag_name")
        if not isinstance(tag_name, str) or not tag_name.strip():
            raise UpdateCheckError(
                UpdateErrorCode.INVALID_RESPONSE,
                "The update response does not contain a release version.",
            )
        payload["tag_name"] = tag_name.strip()
        return payload

    @staticmethod
    def _parse_version(value: object, *, source: str) -> Version:
        if not isinstance(value, str):
            raise UpdateCheckError(
                UpdateErrorCode.INVALID_VERSION,
                f"The {source} version is invalid.",
            )
        normalized = value.strip()
        if normalized.lower().startswith("v"):
            normalized = normalized[1:].strip()
        try:
            return Version(normalized)
        except InvalidVersion as error:
            raise UpdateCheckError(
                UpdateErrorCode.INVALID_VERSION,
                f"The {source} version is invalid.",
                cause=error,
            ) from error

    def _release_url(self, candidate: object) -> str:
        if isinstance(candidate, str) and _is_safe_https_url(candidate):
            return candidate

        fallback = f"{self._project_url.rstrip('/')}/releases/latest"
        if _is_safe_https_url(fallback):
            return fallback
        raise UpdateCheckError(
            UpdateErrorCode.INSECURE_URL,
            "No secure release URL is available.",
        )
