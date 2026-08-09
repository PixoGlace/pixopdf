from __future__ import annotations

import math
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import Final

import pikepdf
from PIL import Image

from pixopdf.pdf.exceptions import PdfRenderError
from pixopdf.pdf.pdfium_renderer import PdfiumRenderer
from pixopdf.pdf.renderer import PdfRenderer


class CompressionError(RuntimeError):
    """Raised when a PDF cannot be compressed safely."""


class CompressionCancelledError(CompressionError):
    """Raised when a caller cancels a compression before publication."""


class CompressionMode(StrEnum):
    PROFILE = "profile"
    TARGET_SIZE = "target_size"
    ADVANCED = "advanced"


class CompressionProfile(StrEnum):
    LIGHT = "light"
    BALANCED = "balanced"
    MAXIMUM = "maximum"


class CompressionStage(StrEnum):
    PREPARING = "preparing"
    OPTIMIZING = "optimizing"
    TESTING = "testing"
    RASTERIZING = "rasterizing"
    SAVING = "saving"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class CompressionProgress:
    percent: int
    stage: CompressionStage
    current: int = 0
    total: int = 0


type ProgressCallback = Callable[[CompressionProgress], None]
type CancelCheck = Callable[[], bool]
type PageProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class CompressionOptions:
    """Validated settings for one compression operation.

    Target sizes use decimal megabytes (1 MB = 1,000,000 bytes), matching the
    values normally shown by desktop file managers.
    """

    mode: CompressionMode = CompressionMode.PROFILE
    profile: CompressionProfile = CompressionProfile.BALANCED
    dpi: int | None = None
    jpeg_quality: int = 82
    target_size_bytes: int | None = None
    allow_raster_fallback: bool = False

    def __post_init__(self) -> None:
        try:
            mode = (
                self.mode if isinstance(self.mode, CompressionMode) else CompressionMode(self.mode)
            )
            profile = (
                self.profile
                if isinstance(self.profile, CompressionProfile)
                else CompressionProfile(self.profile)
            )
        except ValueError as exc:
            raise ValueError("Mode ou profil de compression inconnu") from exc
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "profile", profile)

        if self.dpi is not None and not 72 <= self.dpi <= 600:
            raise ValueError("La résolution doit être comprise entre 72 et 600 DPI")
        if not 35 <= self.jpeg_quality <= 95:
            raise ValueError("La qualité JPEG doit être comprise entre 35 et 95")

        if mode is CompressionMode.PROFILE:
            if self.target_size_bytes is not None or self.dpi is not None:
                raise ValueError("Les réglages personnalisés nécessitent le mode avancé")
            return
        if mode is CompressionMode.ADVANCED and self.dpi is None and self.target_size_bytes is None:
            raise ValueError("Le mode avancé nécessite un DPI ou une taille cible")
        if mode is CompressionMode.TARGET_SIZE and self.target_size_bytes is None:
            raise ValueError("La taille cible doit être indiquée en octets")
        if self.target_size_bytes is not None and isinstance(self.target_size_bytes, bool):
            raise ValueError("La taille cible doit être indiquée en octets")
        if self.target_size_bytes is not None and self.target_size_bytes < 1:
            raise ValueError("La taille cible doit être supérieure à zéro")

    @classmethod
    def for_profile(cls, profile: CompressionProfile | str) -> CompressionOptions:
        return cls(profile=CompressionProfile(profile))

    @classmethod
    def for_target_bytes(
        cls,
        size: int,
        *,
        allow_raster_fallback: bool = False,
    ) -> CompressionOptions:
        return cls(
            mode=CompressionMode.TARGET_SIZE,
            target_size_bytes=size,
            allow_raster_fallback=allow_raster_fallback,
        )

    @classmethod
    def for_target_megabytes(
        cls,
        size: float,
        *,
        allow_raster_fallback: bool = False,
    ) -> CompressionOptions:
        if not math.isfinite(size) or size <= 0:
            raise ValueError("La taille cible en Mo doit être supérieure à zéro")
        return cls.for_target_bytes(
            max(1, round(size * 1_000_000)),
            allow_raster_fallback=allow_raster_fallback,
        )

    @classmethod
    def for_advanced(
        cls,
        *,
        dpi: int | None = None,
        target_size_bytes: int | None = None,
        allow_raster_fallback: bool = False,
    ) -> CompressionOptions:
        return cls(
            mode=CompressionMode.ADVANCED,
            dpi=dpi,
            target_size_bytes=target_size_bytes,
            allow_raster_fallback=allow_raster_fallback,
        )


@dataclass(frozen=True, slots=True)
class CompressionResult:
    source: Path
    destination: Path
    mode: CompressionMode
    profile: CompressionProfile | None
    original_size: int
    compressed_size: int
    target_size_bytes: int | None
    target_reached: bool
    iterations: int
    preserved_text_and_vectors: bool
    rasterized: bool
    applied_dpi: int | None
    applied_jpeg_quality: int | None
    warning: str | None = None

    @property
    def bytes_saved(self) -> int:
        return max(0, self.original_size - self.compressed_size)

    @property
    def reduction_ratio(self) -> float:
        if self.original_size == 0:
            return 0.0
        return self.bytes_saved / self.original_size


@dataclass(frozen=True, slots=True)
class _ImageSettings:
    dpi: int
    jpeg_quality: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: Path
    size: int
    rasterized: bool
    settings: _ImageSettings | None


_PROFILE_SETTINGS: Final[dict[CompressionProfile, _ImageSettings | None]] = {
    CompressionProfile.LIGHT: None,
    CompressionProfile.BALANCED: _ImageSettings(dpi=180, jpeg_quality=82),
    CompressionProfile.MAXIMUM: _ImageSettings(dpi=110, jpeg_quality=58),
}

# Ordered from least to most destructive. The lower bounds are deliberate:
# PixoPDF reports a missed target instead of producing an unreadable document.
_TARGET_VECTOR_SETTINGS: Final[tuple[_ImageSettings | None, ...]] = (
    None,
    _ImageSettings(dpi=240, jpeg_quality=90),
    _ImageSettings(dpi=200, jpeg_quality=85),
    _ImageSettings(dpi=170, jpeg_quality=80),
    _ImageSettings(dpi=140, jpeg_quality=72),
    _ImageSettings(dpi=110, jpeg_quality=62),
    _ImageSettings(dpi=90, jpeg_quality=50),
)
_TARGET_RASTER_SETTINGS: Final[tuple[_ImageSettings, ...]] = (
    _ImageSettings(dpi=120, jpeg_quality=70),
    _ImageSettings(dpi=96, jpeg_quality=55),
    _ImageSettings(dpi=80, jpeg_quality=42),
    _ImageSettings(dpi=72, jpeg_quality=35),
)
MAX_TARGET_ITERATIONS: Final[int] = len(_TARGET_VECTOR_SETTINGS) + len(_TARGET_RASTER_SETTINGS)
_MIN_IMAGE_PIXELS: Final[int] = 100_000


def _advanced_vector_settings(dpi: int) -> tuple[_ImageSettings, ...]:
    return tuple(
        _ImageSettings(dpi=dpi, jpeg_quality=quality) for quality in (90, 82, 72, 62, 50, 35)
    )


def _advanced_raster_settings(dpi: int) -> tuple[_ImageSettings, ...]:
    return tuple(_ImageSettings(dpi=dpi, jpeg_quality=quality) for quality in (70, 55, 42, 35))


class CompressionService:
    """Compress PDFs locally while keeping source files untouched.

    Profile compression edits only raster image XObjects and the PDF container;
    text, vector paths and page content streams remain vectorial. Target mode
    tries the same safe candidates first. When explicitly allowed, an unmet
    target may trigger a bounded full-page raster fallback disclosed in the result.
    """

    def __init__(self, renderer: PdfRenderer | None = None) -> None:
        self.renderer = renderer or PdfiumRenderer()

    def compress(
        self,
        source: Path,
        destination: Path,
        options: CompressionOptions | None = None,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> CompressionResult:
        selected = options or CompressionOptions()
        _check_cancelled(cancelled)
        _emit_progress(progress, 0, CompressionStage.PREPARING)
        source_path = Path(source).expanduser()
        destination_path = Path(destination).expanduser()
        if not source_path.is_file():
            raise FileNotFoundError(f"Fichier PDF introuvable : {source_path}")
        if source_path.resolve() == destination_path.resolve():
            raise ValueError("La destination doit être différente du fichier source")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        original_size = source_path.stat().st_size

        try:
            with tempfile.TemporaryDirectory(
                prefix=f".{destination_path.stem}-compression-",
                dir=destination_path.parent,
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                if selected.mode is CompressionMode.PROFILE:
                    result = self._compress_profile(
                        source_path,
                        destination_path,
                        temporary_root,
                        original_size,
                        selected,
                        progress,
                        cancelled,
                    )
                elif selected.target_size_bytes is not None:
                    result = self._compress_to_target(
                        source_path,
                        destination_path,
                        temporary_root,
                        original_size,
                        selected,
                        progress,
                        cancelled,
                    )
                else:
                    result = self._compress_advanced_dpi(
                        source_path,
                        destination_path,
                        temporary_root,
                        original_size,
                        selected,
                        progress,
                        cancelled,
                    )
        except (OSError, PdfRenderError, pikepdf.PdfError, pikepdf.PasswordError) as exc:
            raise CompressionError(f"Impossible de compresser {source_path.name}") from exc
        return result

    def _compress_profile(
        self,
        source: Path,
        destination: Path,
        temporary_root: Path,
        original_size: int,
        options: CompressionOptions,
        progress: ProgressCallback | None,
        cancelled: CancelCheck | None,
    ) -> CompressionResult:
        candidate_path = temporary_root / "profile.pdf"
        settings = _PROFILE_SETTINGS[options.profile]

        def report_page(current: int, total: int) -> None:
            _emit_progress(
                progress,
                5 + round(82 * current / max(1, total)),
                CompressionStage.OPTIMIZING,
                current,
                total,
            )

        _emit_progress(progress, 5, CompressionStage.OPTIMIZING)
        _write_vector_preserving_candidate(
            source,
            candidate_path,
            settings,
            cancelled=cancelled,
            page_progress=report_page,
        )
        _check_cancelled(cancelled)
        candidate = _Candidate(candidate_path, candidate_path.stat().st_size, False, settings)
        baseline = _copy_candidate(source, temporary_root / "source.pdf")
        chosen = min((baseline, candidate), key=lambda item: item.size)
        _emit_progress(progress, 94, CompressionStage.SAVING)
        _check_cancelled(cancelled)
        os.replace(chosen.path, destination)
        warning = None
        if chosen.size >= original_size:
            warning = (
                "Le PDF source est déjà optimisé ; la sortie ne peut pas être réduite davantage."
            )
        result = CompressionResult(
            source=source,
            destination=destination,
            mode=options.mode,
            profile=options.profile,
            original_size=original_size,
            compressed_size=chosen.size,
            target_size_bytes=None,
            target_reached=True,
            iterations=1,
            preserved_text_and_vectors=True,
            rasterized=False,
            applied_dpi=chosen.settings.dpi if chosen.settings else None,
            applied_jpeg_quality=(
                chosen.settings.jpeg_quality if chosen.settings is not None else None
            ),
            warning=warning,
        )
        _emit_progress(progress, 100, CompressionStage.COMPLETE)
        return result

    def _compress_advanced_dpi(
        self,
        source: Path,
        destination: Path,
        temporary_root: Path,
        original_size: int,
        options: CompressionOptions,
        progress: ProgressCallback | None,
        cancelled: CancelCheck | None,
    ) -> CompressionResult:
        if options.dpi is None:
            raise ValueError("La résolution avancée est manquante")
        settings = _ImageSettings(options.dpi, options.jpeg_quality)
        candidate_path = temporary_root / "advanced.pdf"

        def report_page(current: int, total: int) -> None:
            _emit_progress(
                progress,
                5 + round(82 * current / max(1, total)),
                CompressionStage.OPTIMIZING,
                current,
                total,
            )

        _emit_progress(progress, 5, CompressionStage.OPTIMIZING)
        _write_vector_preserving_candidate(
            source,
            candidate_path,
            settings,
            cancelled=cancelled,
            page_progress=report_page,
        )
        _check_cancelled(cancelled)
        candidate = _Candidate(candidate_path, candidate_path.stat().st_size, False, settings)
        baseline = _copy_candidate(source, temporary_root / "source.pdf")
        chosen = min((baseline, candidate), key=lambda item: item.size)
        _emit_progress(progress, 94, CompressionStage.SAVING)
        _check_cancelled(cancelled)
        os.replace(chosen.path, destination)
        result = CompressionResult(
            source=source,
            destination=destination,
            mode=options.mode,
            profile=None,
            original_size=original_size,
            compressed_size=chosen.size,
            target_size_bytes=None,
            target_reached=True,
            iterations=1,
            preserved_text_and_vectors=True,
            rasterized=False,
            applied_dpi=chosen.settings.dpi if chosen.settings else None,
            applied_jpeg_quality=(
                chosen.settings.jpeg_quality if chosen.settings is not None else None
            ),
            warning=(
                "Le PDF source est déjà optimisé ; la sortie ne peut pas être réduite davantage."
                if chosen.size >= original_size
                else None
            ),
        )
        _emit_progress(progress, 100, CompressionStage.COMPLETE)
        return result

    def _compress_to_target(
        self,
        source: Path,
        destination: Path,
        temporary_root: Path,
        original_size: int,
        options: CompressionOptions,
        progress: ProgressCallback | None,
        cancelled: CancelCheck | None,
    ) -> CompressionResult:
        target = options.target_size_bytes
        if target is None:  # Protected by CompressionOptions, useful for type narrowing.
            raise ValueError("La taille cible est manquante")

        baseline = _copy_candidate(source, temporary_root / "source.pdf")
        if baseline.size <= target:
            _check_cancelled(cancelled)
            os.replace(baseline.path, destination)
            result = CompressionResult(
                source=source,
                destination=destination,
                mode=options.mode,
                profile=None,
                original_size=original_size,
                compressed_size=baseline.size,
                target_size_bytes=target,
                target_reached=True,
                iterations=0,
                preserved_text_and_vectors=True,
                rasterized=False,
                applied_dpi=None,
                applied_jpeg_quality=None,
                warning=(
                    "Le fichier source respectait déjà la taille cible ; il a été copié sans perte."
                ),
            )
            _emit_progress(progress, 100, CompressionStage.COMPLETE)
            return result

        vector_settings = (
            _advanced_vector_settings(options.dpi)
            if options.mode is CompressionMode.ADVANCED and options.dpi is not None
            else _TARGET_VECTOR_SETTINGS
        )
        raster_settings = (
            _advanced_raster_settings(options.dpi)
            if options.mode is CompressionMode.ADVANCED and options.dpi is not None
            else _TARGET_RASTER_SETTINGS
        )
        total_attempts = len(vector_settings) + (
            len(raster_settings) if options.allow_raster_fallback else 0
        )
        best = baseline
        iterations = 0
        chosen: _Candidate | None = None
        for index, settings in enumerate(vector_settings, start=1):
            _check_cancelled(cancelled)
            candidate_path = temporary_root / f"vector-{index}.pdf"

            completed_attempts = iterations

            def report_vector_page(
                current: int,
                total: int,
                base: int = completed_attempts,
            ) -> None:
                completed = base + current / max(1, total)
                _emit_progress(
                    progress,
                    4 + round(88 * completed / max(1, total_attempts)),
                    CompressionStage.TESTING,
                    base + 1,
                    total_attempts,
                )

            _emit_progress(
                progress,
                4 + round(88 * iterations / max(1, total_attempts)),
                CompressionStage.TESTING,
                iterations + 1,
                total_attempts,
            )
            _write_vector_preserving_candidate(
                source,
                candidate_path,
                settings,
                cancelled=cancelled,
                page_progress=report_vector_page,
            )
            _check_cancelled(cancelled)
            candidate = _Candidate(candidate_path, candidate_path.stat().st_size, False, settings)
            iterations += 1
            if candidate.size <= target:
                best.path.unlink(missing_ok=True)
                chosen = candidate
                break
            best = _retain_smaller_candidate(best, candidate)

        if (
            chosen is None
            and options.allow_raster_fallback
            and iterations < len(vector_settings) + len(raster_settings)
        ):
            for index, settings in enumerate(raster_settings, start=1):
                _check_cancelled(cancelled)
                candidate_path = temporary_root / f"raster-{index}.pdf"

                completed_attempts = iterations

                def report_raster_page(
                    current: int,
                    total: int,
                    base: int = completed_attempts,
                ) -> None:
                    completed = base + current / max(1, total)
                    _emit_progress(
                        progress,
                        4 + round(88 * completed / max(1, total_attempts)),
                        CompressionStage.RASTERIZING,
                        base + 1,
                        total_attempts,
                    )

                _emit_progress(
                    progress,
                    4 + round(88 * iterations / max(1, total_attempts)),
                    CompressionStage.RASTERIZING,
                    iterations + 1,
                    total_attempts,
                )
                self._write_raster_candidate(
                    source,
                    candidate_path,
                    settings,
                    cancelled=cancelled,
                    page_progress=report_raster_page,
                )
                _check_cancelled(cancelled)
                candidate = _Candidate(
                    candidate_path,
                    candidate_path.stat().st_size,
                    True,
                    settings,
                )
                iterations += 1
                if candidate.size <= target:
                    best.path.unlink(missing_ok=True)
                    chosen = candidate
                    break
                best = _retain_smaller_candidate(best, candidate)

        if chosen is None:
            chosen = best
        target_reached = chosen.size <= target
        warning = _target_warning(chosen, target_reached, target, options.allow_raster_fallback)
        _emit_progress(progress, 96, CompressionStage.SAVING)
        _check_cancelled(cancelled)
        os.replace(chosen.path, destination)
        result = CompressionResult(
            source=source,
            destination=destination,
            mode=options.mode,
            profile=None,
            original_size=original_size,
            compressed_size=chosen.size,
            target_size_bytes=target,
            target_reached=target_reached,
            iterations=iterations,
            preserved_text_and_vectors=not chosen.rasterized,
            rasterized=chosen.rasterized,
            applied_dpi=chosen.settings.dpi if chosen.settings else None,
            applied_jpeg_quality=(
                chosen.settings.jpeg_quality if chosen.settings is not None else None
            ),
            warning=warning,
        )
        _emit_progress(progress, 100, CompressionStage.COMPLETE)
        return result

    def _write_raster_candidate(
        self,
        source: Path,
        destination: Path,
        settings: _ImageSettings,
        *,
        cancelled: CancelCheck | None,
        page_progress: PageProgressCallback | None,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.stem}-pages-",
            dir=destination.parent,
        ) as page_directory_name:
            page_directory = Path(page_directory_name)
            output = pikepdf.Pdf.new()
            try:
                with pikepdf.open(source) as original:
                    page_count = len(original.pages)
                    page_sizes: list[tuple[float, float]] = []
                    for page in original.pages:
                        media_box = [float(value) for value in page.mediabox]
                        width = abs(media_box[2] - media_box[0])
                        height = abs(media_box[3] - media_box[1])
                        rotation = int(page.obj.get("/Rotate", 0)) % 360
                        page_sizes.append(
                            (height, width) if rotation in {90, 270} else (width, height)
                        )
                if page_count < 1:
                    raise CompressionError("Le PDF ne contient aucune page")
                for page_index, (width, height) in enumerate(page_sizes):
                    _check_cancelled(cancelled)
                    pixel_width = max(1, math.ceil(width / 72 * settings.dpi))
                    pixel_height = max(1, math.ceil(height / 72 * settings.dpi))
                    png_data = self.renderer.render_page(
                        source,
                        page_index,
                        pixel_width,
                        pixel_height,
                    )
                    page_pdf_path = page_directory / f"page-{page_index:05d}.pdf"
                    with Image.open(BytesIO(png_data)) as rendered:
                        rgb = _flatten_for_jpeg(rendered)
                        try:
                            rgb.save(
                                page_pdf_path,
                                format="PDF",
                                resolution=settings.dpi,
                                quality=settings.jpeg_quality,
                                optimize=True,
                            )
                        finally:
                            if rgb is not rendered:
                                rgb.close()
                    with pikepdf.open(page_pdf_path) as page_pdf:
                        output.pages.append(page_pdf.pages[0])
                    page_pdf_path.unlink(missing_ok=True)
                    if page_progress is not None:
                        page_progress(page_index + 1, page_count)
                _check_cancelled(cancelled)
                output.save(
                    destination,
                    compress_streams=True,
                    object_stream_mode=pikepdf.ObjectStreamMode.generate,
                    recompress_flate=True,
                )
            finally:
                output.close()


def _check_cancelled(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise CompressionCancelledError("Compression annulée")


def _emit_progress(
    callback: ProgressCallback | None,
    percent: int,
    stage: CompressionStage,
    current: int = 0,
    total: int = 0,
) -> None:
    if callback is not None:
        callback(
            CompressionProgress(
                percent=max(0, min(100, percent)),
                stage=stage,
                current=current,
                total=total,
            )
        )


def _copy_candidate(source: Path, destination: Path) -> _Candidate:
    shutil.copyfile(source, destination)
    return _Candidate(destination, destination.stat().st_size, False, None)


def _retain_smaller_candidate(first: _Candidate, second: _Candidate) -> _Candidate:
    if second.size < first.size:
        first.path.unlink(missing_ok=True)
        return second
    second.path.unlink(missing_ok=True)
    return first


def _target_warning(
    candidate: _Candidate,
    target_reached: bool,
    target: int,
    raster_fallback_allowed: bool,
) -> str | None:
    messages: list[str] = []
    if candidate.rasterized:
        messages.append(
            "La taille cible a nécessité une rasterisation : le texte n’est plus "
            "sélectionnable, les éléments vectoriels ont été convertis en images, et les "
            "liens, formulaires ou calques interactifs ne sont plus conservés."
        )
    if not target_reached:
        fallback_note = (
            " Les limites minimales sont 72 ppp et une qualité JPEG de 35."
            if raster_fallback_allowed
            else " La rasterisation de secours était désactivée."
        )
        messages.append(
            f"La cible de {target} octets n’a pas pu être atteinte sans dépasser les "
            f"limites de qualité.{fallback_note} Taille obtenue : {candidate.size} octets."
        )
    return " ".join(messages) or None


def _write_vector_preserving_candidate(
    source: Path,
    destination: Path,
    settings: _ImageSettings | None,
    *,
    cancelled: CancelCheck | None,
    page_progress: PageProgressCallback | None,
) -> None:
    _check_cancelled(cancelled)
    with pikepdf.open(source) as pdf:
        if settings is not None:
            _recompress_document_images(
                pdf,
                settings,
                cancelled=cancelled,
                page_progress=page_progress,
            )
        elif page_progress is not None:
            page_progress(1, 1)
        _check_cancelled(cancelled)
        pdf.remove_unreferenced_resources()
        pdf.save(
            destination,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            recompress_flate=True,
        )


def _recompress_document_images(
    pdf: pikepdf.Pdf,
    settings: _ImageSettings,
    *,
    cancelled: CancelCheck | None,
    page_progress: PageProgressCallback | None,
) -> None:
    visited: set[tuple[int, int] | tuple[str, int]] = set()
    page_count = len(pdf.pages)
    for page_index, page in enumerate(pdf.pages):
        _check_cancelled(cancelled)
        media_box = [float(value) for value in page.mediabox]
        page_size = (abs(media_box[2] - media_box[0]), abs(media_box[3] - media_box[1]))
        resources = page.obj.get("/Resources")
        if resources is not None:
            _recompress_resources(
                resources,
                page_size,
                settings,
                visited,
                cancelled=cancelled,
            )
        if page_progress is not None:
            page_progress(page_index + 1, page_count)


def _recompress_resources(
    resources: pikepdf.Object,
    page_size: tuple[float, float],
    settings: _ImageSettings,
    visited: set[tuple[int, int] | tuple[str, int]],
    *,
    cancelled: CancelCheck | None,
) -> None:
    xobjects = resources.get("/XObject")
    if xobjects is None:
        return
    for name in list(xobjects.keys()):
        _check_cancelled(cancelled)
        image_object = xobjects[name]
        key: tuple[int, int] | tuple[str, int]
        object_generation = image_object.objgen
        key = object_generation if object_generation != (0, 0) else ("direct", id(image_object))
        if key in visited:
            continue
        visited.add(key)
        subtype = image_object.get("/Subtype")
        if subtype == pikepdf.Name.Image:
            _recompress_image(image_object, page_size, settings)
        elif subtype == pikepdf.Name.Form:
            child_resources = image_object.get("/Resources")
            if child_resources is not None:
                _recompress_resources(
                    child_resources,
                    page_size,
                    settings,
                    visited,
                    cancelled=cancelled,
                )


def _recompress_image(
    image_object: pikepdf.Object,
    page_size: tuple[float, float],
    settings: _ImageSettings,
) -> None:
    if image_object.get("/SMask") is not None or image_object.get("/Mask") is not None:
        return
    try:
        pdf_image = pikepdf.PdfImage(image_object)  # type: ignore[arg-type]
        if pdf_image.image_mask or pdf_image.bits_per_component != 8:
            return
        if pdf_image.width * pdf_image.height < _MIN_IMAGE_PIXELS:
            return
        original_stream_size = len(image_object.read_raw_bytes())
        pil_image = pdf_image.as_pil_image()
    except (OSError, ValueError, pikepdf.PdfError, pikepdf.UnsupportedImageTypeError):
        return

    try:
        prepared = _prepare_image(pil_image, page_size, settings.dpi)
        try:
            encoded = BytesIO()
            prepared.save(
                encoded,
                format="JPEG",
                quality=settings.jpeg_quality,
                optimize=True,
            )
            jpeg_data = encoded.getvalue()
            if len(jpeg_data) >= original_stream_size:
                return
            color_space = (
                pikepdf.Name.DeviceGray if prepared.mode == "L" else pikepdf.Name.DeviceRGB
            )
            image_object.write(jpeg_data, filter=pikepdf.Name.DCTDecode)
            image_object["/Type"] = pikepdf.Name.XObject
            image_object["/Subtype"] = pikepdf.Name.Image
            image_object["/Width"] = prepared.width
            image_object["/Height"] = prepared.height
            image_object["/BitsPerComponent"] = 8
            image_object["/ColorSpace"] = color_space
            for key in ("/Decode", "/DecodeParms", "/Intent", "/ICCProfile"):
                if key in image_object:
                    del image_object[key]
        finally:
            if prepared is not pil_image:
                prepared.close()
    finally:
        pil_image.close()


def _prepare_image(
    image: Image.Image,
    page_size: tuple[float, float],
    dpi: int,
) -> Image.Image:
    prepared = image
    if image.mode not in {"L", "RGB"}:
        prepared = image.convert("RGB")
    maximum_width = max(1, round(page_size[0] / 72 * dpi))
    maximum_height = max(1, round(page_size[1] / 72 * dpi))
    ratio = min(1.0, maximum_width / prepared.width, maximum_height / prepared.height)
    if ratio >= 1.0:
        return prepared
    resized = prepared.resize(
        (max(1, round(prepared.width * ratio)), max(1, round(prepared.height * ratio))),
        Image.Resampling.LANCZOS,
    )
    if prepared is not image:
        prepared.close()
    return resized


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, "white")
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        rgba.close()
        return flattened
    return image.convert("RGB")
