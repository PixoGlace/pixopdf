from pathlib import Path

import pikepdf
import pytest

from pixopdf.services import compression_service
from pixopdf.services.compression_service import (
    MAX_TARGET_ITERATIONS,
    CompressionError,
    CompressionMode,
    CompressionOptions,
    CompressionProfile,
    CompressionService,
)


def create_small_pdf(path: Path) -> None:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page()
    pdf.save(path)
    pdf.close()


def test_compression_options_support_profiles_bytes_and_decimal_megabytes() -> None:
    profile = CompressionOptions.for_profile("maximum")
    target_bytes = CompressionOptions.for_target_bytes(123_456)
    target_megabytes = CompressionOptions.for_target_megabytes(1.25)
    advanced = CompressionOptions.for_advanced(dpi=144, target_size_bytes=900_000)

    assert profile.mode is CompressionMode.PROFILE
    assert profile.profile is CompressionProfile.MAXIMUM
    assert profile.target_size_bytes is None
    assert target_bytes.mode is CompressionMode.TARGET_SIZE
    assert target_bytes.target_size_bytes == 123_456
    assert target_megabytes.target_size_bytes == 1_250_000
    assert advanced.mode is CompressionMode.ADVANCED
    assert advanced.dpi == 144
    assert advanced.target_size_bytes == 900_000
    assert MAX_TARGET_ITERATIONS > 0


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CompressionOptions(mode=CompressionMode.TARGET_SIZE),
        lambda: CompressionOptions.for_target_bytes(0),
        lambda: CompressionOptions.for_target_megabytes(float("inf")),
        lambda: CompressionOptions(target_size_bytes=100),
        lambda: CompressionOptions.for_advanced(),
        lambda: CompressionOptions.for_advanced(dpi=50),
    ],
)
def test_compression_options_reject_invalid_target_settings(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]


def test_compression_rejects_a_source_as_its_own_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    create_small_pdf(source)

    with pytest.raises(ValueError, match="différente"):
        CompressionService().compress(source, source)


def test_target_larger_than_source_is_an_atomic_lossless_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "nested" / "compressed.pdf"
    create_small_pdf(source)
    original = source.read_bytes()

    result = CompressionService().compress(
        source,
        destination,
        CompressionOptions.for_target_bytes(len(original) + 1),
    )

    assert destination.read_bytes() == original
    assert source.read_bytes() == original
    assert result.target_reached
    assert result.iterations == 0
    assert result.preserved_text_and_vectors
    assert not result.rasterized
    assert result.warning is not None


def test_failed_candidate_keeps_source_and_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "destination.pdf"
    create_small_pdf(source)
    original = source.read_bytes()
    destination.write_bytes(b"existing destination")

    def fail_after_partial_write(
        _source: Path,
        temporary_destination: Path,
        _settings: object,
    ) -> None:
        temporary_destination.write_bytes(b"partial")
        raise OSError("simulated failure")

    monkeypatch.setattr(
        compression_service,
        "_write_vector_preserving_candidate",
        fail_after_partial_write,
    )

    with pytest.raises(CompressionError, match="Impossible de compresser"):
        CompressionService().compress(source, destination)

    assert source.read_bytes() == original
    assert destination.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(".*-compression-*")) == []
