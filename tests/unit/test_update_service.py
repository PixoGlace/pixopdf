import json
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from pixopdf.services.update_service import (
    MAX_UPDATE_PAYLOAD_BYTES,
    UpdateCheckError,
    UpdateErrorCode,
    UpdateResult,
    UpdateService,
    UpdateStatus,
)


class RecordingFetcher:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()
        self.calls: list[tuple[str, float, int]] = []

    def __call__(self, url: str, timeout: float, max_bytes: int) -> bytes:
        self.calls.append((url, timeout, max_bytes))
        return self.payload


def test_check_reports_available_update_and_normalizes_versions() -> None:
    fetcher = RecordingFetcher(
        {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/PixoGlace/pixopdf/releases/tag/v0.2.0",
            "body": "Corrections and improvements.",
        }
    )
    service = UpdateService(fetcher=fetcher, timeout=3.5)

    result = service.check("0.1.0")

    assert result == UpdateResult(
        status=UpdateStatus.AVAILABLE,
        current_version="0.1.0",
        latest_version="0.2.0",
        release_url="https://github.com/PixoGlace/pixopdf/releases/tag/v0.2.0",
        release_notes="Corrections and improvements.",
    )
    assert fetcher.calls == [
        (
            "https://api.github.com/repos/PixoGlace/pixopdf/releases/latest",
            3.5,
            MAX_UPDATE_PAYLOAD_BYTES,
        )
    ]


@pytest.mark.parametrize("latest_version", ["0.1.0", "0.0.9"])
def test_check_reports_current_for_equal_or_older_release(latest_version: str) -> None:
    service = UpdateService(fetcher=RecordingFetcher({"tag_name": latest_version}))

    result = service.check("0.1.0")

    assert result.status is UpdateStatus.CURRENT
    assert result.latest_version == latest_version


def test_pep_440_comparison_handles_prereleases() -> None:
    service = UpdateService(fetcher=RecordingFetcher({"tag_name": "v1.0.0"}))

    result = service.check("1.0.0rc1")

    assert result.status is UpdateStatus.AVAILABLE


@pytest.mark.parametrize("release_url", [None, "", "http://example.com/release", "javascript:x"])
def test_missing_or_unsafe_release_url_uses_secure_project_fallback(
    release_url: object,
) -> None:
    service = UpdateService(
        project_url="https://example.com/pixopdf",
        fetcher=RecordingFetcher({"tag_name": "0.2.0", "html_url": release_url, "body": None}),
    )

    result = service.check("0.1.0")

    assert result.release_url == "https://example.com/pixopdf/releases/latest"
    assert result.release_notes == ""


def test_check_rejects_insecure_update_endpoint_without_fetching() -> None:
    fetcher = RecordingFetcher({"tag_name": "0.2.0"})
    service = UpdateService(
        update_url="http://example.com/releases/latest",
        fetcher=fetcher,
    )

    with pytest.raises(UpdateCheckError) as raised:
        service.check("0.1.0")

    assert raised.value.code is UpdateErrorCode.INSECURE_URL
    assert fetcher.calls == []


def test_check_rejects_insecure_fallback_when_payload_has_no_safe_url() -> None:
    service = UpdateService(
        project_url="http://example.com/pixopdf",
        fetcher=RecordingFetcher({"tag_name": "0.2.0"}),
    )

    with pytest.raises(UpdateCheckError) as raised:
        service.check("0.1.0")

    assert raised.value.code is UpdateErrorCode.INSECURE_URL


def test_check_enforces_payload_limit_even_for_injected_fetcher() -> None:
    def oversized_fetcher(url: str, timeout: float, max_bytes: int) -> bytes:
        del url, timeout
        return b"x" * (max_bytes + 1)

    service = UpdateService(fetcher=oversized_fetcher, max_payload_bytes=32)

    with pytest.raises(UpdateCheckError) as raised:
        service.check("0.1.0")

    assert raised.value.code is UpdateErrorCode.PAYLOAD_TOO_LARGE


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (b"not json", UpdateErrorCode.INVALID_RESPONSE),
        (b"[]", UpdateErrorCode.INVALID_RESPONSE),
        (b"{}", UpdateErrorCode.INVALID_RESPONSE),
        (json.dumps({"tag_name": 12}).encode(), UpdateErrorCode.INVALID_RESPONSE),
        (json.dumps({"tag_name": "not a version"}).encode(), UpdateErrorCode.INVALID_VERSION),
    ],
)
def test_check_returns_structured_errors_for_bad_responses(
    payload: bytes,
    expected_code: UpdateErrorCode,
) -> None:
    def fetcher(url: str, timeout: float, max_bytes: int) -> bytes:
        del url, timeout, max_bytes
        return payload

    with pytest.raises(UpdateCheckError) as raised:
        UpdateService(fetcher=fetcher).check("0.1.0")

    assert raised.value.code is expected_code
    assert raised.value.message


def test_check_returns_structured_error_for_invalid_installed_version() -> None:
    service = UpdateService(fetcher=RecordingFetcher({"tag_name": "0.2.0"}))

    with pytest.raises(UpdateCheckError) as raised:
        service.check("development")

    assert raised.value.code is UpdateErrorCode.INVALID_VERSION


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (URLError("offline"), UpdateErrorCode.NETWORK),
        (
            HTTPError("https://example.com", 503, "Unavailable", Message(), None),
            UpdateErrorCode.HTTP,
        ),
    ],
)
def test_check_maps_transport_failures_to_structured_errors(
    error: Exception,
    expected_code: UpdateErrorCode,
) -> None:
    def failing_fetcher(url: str, timeout: float, max_bytes: int) -> bytes:
        del url, timeout, max_bytes
        raise error

    with pytest.raises(UpdateCheckError) as raised:
        UpdateService(fetcher=failing_fetcher).check()

    assert raised.value.code is expected_code
    assert raised.value.cause is error


@pytest.mark.parametrize(
    ("timeout", "max_payload_bytes"),
    [(0.0, MAX_UPDATE_PAYLOAD_BYTES), (1.0, 0)],
)
def test_constructor_rejects_invalid_limits(
    timeout: float,
    max_payload_bytes: int,
) -> None:
    with pytest.raises(ValueError):
        UpdateService(timeout=timeout, max_payload_bytes=max_payload_bytes)
