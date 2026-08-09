"""Local conversion workflows with transactional output publication."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pikepdf
import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image, ImageOps

from pixopdf.pdf.pdfium_renderer import _PDFIUM_RENDER_LOCK

from ._atomic import (
    atomic_file,
    ensure_distinct_destination,
    publish_staged_files,
    staging_directory,
)


class RasterImageFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"

    @property
    def suffix(self) -> str:
        return ".jpg" if self is RasterImageFormat.JPEG else ".png"


@dataclass(frozen=True, slots=True)
class PdfToImagesOptions:
    image_format: RasterImageFormat = RasterImageFormat.PNG
    dpi: int = 144
    jpeg_quality: int = 90
    png_compress_level: int = 6
    background_color: tuple[int, int, int] = (255, 255, 255)

    def __post_init__(self) -> None:
        if not 36 <= self.dpi <= 1200:
            raise ValueError("La résolution doit être comprise entre 36 et 1200 DPI")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("La qualité JPEG doit être comprise entre 1 et 100")
        if not 0 <= self.png_compress_level <= 9:
            raise ValueError("La compression PNG doit être comprise entre 0 et 9")
        _validate_rgb(self.background_color)


@dataclass(frozen=True, slots=True)
class ImagesToPdfOptions:
    dpi: float = 150.0
    jpeg_quality: int = 92
    optimize: bool = True
    background_color: tuple[int, int, int] = (255, 255, 255)

    def __post_init__(self) -> None:
        if not 36.0 <= self.dpi <= 1200.0:
            raise ValueError("La résolution doit être comprise entre 36 et 1200 DPI")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("La qualité doit être comprise entre 1 et 100")
        _validate_rgb(self.background_color)


@dataclass(frozen=True, slots=True)
class ExtractImagesOptions:
    recursive: bool = True
    deduplicate: bool = True
    apply_decode_array: bool = True
    apply_mask: bool = True


class ConversionService:
    """Convert PDF pages and raster images without changing source files."""

    def pdf_to_images(
        self,
        source: Path,
        destination: Path,
        options: PdfToImagesOptions | None = None,
    ) -> list[Path]:
        selected = options or PdfToImagesOptions()
        _require_file(source)
        with staging_directory(destination) as staging:
            with _PDFIUM_RENDER_LOCK:
                document = pdfium.PdfDocument(source)
                try:
                    page_count = len(document)
                    if page_count < 1:
                        raise ValueError("Le PDF ne contient aucune page")
                    width = max(3, len(str(page_count)))
                    relative_names: list[Path] = []
                    for page_index in range(page_count):
                        relative_name = Path(
                            f"{source.stem}-page-{page_index + 1:0{width}d}"
                            f"{selected.image_format.suffix}"
                        )
                        self._render_page(
                            document,
                            page_index,
                            staging / relative_name,
                            selected,
                        )
                        relative_names.append(relative_name)
                finally:
                    document.close()
            return publish_staged_files(staging, destination, relative_names)

    def images_to_pdf(
        self,
        sources: Sequence[Path],
        destination: Path,
        options: ImagesToPdfOptions | None = None,
    ) -> Path:
        selected = options or ImagesToPdfOptions()
        source_paths = list(sources)
        if not source_paths:
            raise ValueError("Ajoutez au moins une image")
        for source in source_paths:
            _require_file(source)
        ensure_distinct_destination(destination, source_paths)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with (
            TemporaryDirectory(
                prefix=f".{destination.stem}-images-",
                dir=destination.parent,
            ) as staging_name,
            pikepdf.Pdf.new() as output,
        ):
            staging = Path(staging_name)
            for index, source in enumerate(source_paths):
                page_path = staging / f"page-{index:05d}.pdf"
                with Image.open(source) as opened:
                    transposed = ImageOps.exif_transpose(opened)
                    try:
                        prepared = _flatten_to_rgb(transposed, selected.background_color)
                        try:
                            prepared.save(
                                page_path,
                                format="PDF",
                                resolution=selected.dpi,
                                quality=selected.jpeg_quality,
                                optimize=selected.optimize,
                            )
                        finally:
                            prepared.close()
                    finally:
                        if transposed is not opened:
                            transposed.close()
                with pikepdf.open(page_path) as page_pdf:
                    output.pages.append(page_pdf.pages[0])
                page_path.unlink(missing_ok=True)
            with atomic_file(destination, source_paths) as temporary:
                output.save(temporary)
        return destination

    def extract_images(
        self,
        source: Path,
        destination: Path,
        options: ExtractImagesOptions | None = None,
    ) -> list[Path]:
        selected = options or ExtractImagesOptions()
        _require_file(source)
        with staging_directory(destination) as staging, pikepdf.open(source) as document:
            relative_names: list[Path] = []
            seen_digests: set[bytes] = set()
            page_width = max(3, len(str(len(document.pages))))
            for page_number, page in enumerate(document.pages, start=1):
                images = page.get_images(recursive=selected.recursive)
                image_width = max(2, len(str(len(images))))
                for image_number, image_object in enumerate(images.values(), start=1):
                    stream = BytesIO()
                    extension = pikepdf.PdfImage(cast(pikepdf.Stream, image_object)).extract_to(
                        stream=stream,
                        apply_decode_array=selected.apply_decode_array,
                        apply_mask=selected.apply_mask,
                    )
                    payload = stream.getvalue()
                    digest = sha256(payload).digest()
                    if selected.deduplicate and digest in seen_digests:
                        continue
                    seen_digests.add(digest)
                    suffix = _safe_image_suffix(extension)
                    relative_name = Path(
                        f"{source.stem}-page-{page_number:0{page_width}d}"
                        f"-image-{image_number:0{image_width}d}{suffix}"
                    )
                    (staging / relative_name).write_bytes(payload)
                    relative_names.append(relative_name)
            return publish_staged_files(staging, destination, relative_names)

    @staticmethod
    def _render_page(
        document: object,
        page_index: int,
        destination: Path,
        options: PdfToImagesOptions,
    ) -> None:
        page = document[page_index]  # type: ignore[index]
        try:
            bitmap = page.render(scale=options.dpi / 72.0)
            try:
                rendered = bitmap.to_pil()
                try:
                    if options.image_format is RasterImageFormat.JPEG:
                        converted = _flatten_to_rgb(rendered, options.background_color)
                        try:
                            converted.save(
                                destination,
                                format="JPEG",
                                quality=options.jpeg_quality,
                                optimize=True,
                            )
                        finally:
                            converted.close()
                    else:
                        converted = rendered.convert("RGBA")
                        try:
                            converted.save(
                                destination,
                                format="PNG",
                                compress_level=options.png_compress_level,
                            )
                        finally:
                            converted.close()
                finally:
                    rendered.close()
            finally:
                bitmap.close()
        finally:
            page.close()


def _flatten_to_rgb(
    image: Image.Image,
    background_color: tuple[int, int, int],
) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        try:
            background = Image.new("RGB", rgba.size, background_color)
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        finally:
            rgba.close()
    return image.convert("RGB")


def _validate_rgb(color: tuple[int, int, int]) -> None:
    if len(color) != 3 or any(component < 0 or component > 255 for component in color):
        raise ValueError("La couleur de fond doit contenir trois valeurs comprises entre 0 et 255")


def _safe_image_suffix(extension: str) -> str:
    normalized = extension.lower()
    if normalized not in {".jpg", ".jpeg", ".jp2", ".png", ".tif", ".tiff"}:
        raise ValueError(f"Format d’image PDF non pris en charge : {extension}")
    return ".jpg" if normalized == ".jpeg" else normalized


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
