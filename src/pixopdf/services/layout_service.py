"""Page-format and N-up layout operations implemented with pikepdf overlays."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pikepdf

from ._atomic import atomic_file


class PageFormat(StrEnum):
    A3 = "a3"
    A4 = "a4"
    A5 = "a5"
    LETTER = "letter"
    LEGAL = "legal"


class PageOrientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


PAGE_SIZES: dict[PageFormat, tuple[float, float]] = {
    PageFormat.A3: (841.89, 1190.55),
    PageFormat.A4: (595.28, 841.89),
    PageFormat.A5: (419.53, 595.28),
    PageFormat.LETTER: (612.0, 792.0),
    PageFormat.LEGAL: (612.0, 1008.0),
}


@dataclass(frozen=True, slots=True)
class TargetFormatOptions:
    page_format: PageFormat = PageFormat.A4
    orientation: PageOrientation = PageOrientation.PORTRAIT
    margin_points: float = 0.0
    allow_upscale: bool = True

    def __post_init__(self) -> None:
        _validate_non_negative("La marge", self.margin_points)
        _validate_usable_page(self.page_size, self.margin_points, 0.0, 1, 1)

    @property
    def page_size(self) -> tuple[float, float]:
        return resolve_page_size(self.page_format, self.orientation)


@dataclass(frozen=True, slots=True)
class NUpOptions:
    rows: int = 2
    columns: int = 2
    page_format: PageFormat = PageFormat.A4
    orientation: PageOrientation = PageOrientation.LANDSCAPE
    margin_points: float = 18.0
    gutter_points: float = 12.0
    allow_upscale: bool = True

    def __post_init__(self) -> None:
        if self.rows < 1 or self.columns < 1:
            raise ValueError("Le nombre de lignes et de colonnes doit être positif")
        if self.rows * self.columns > 64:
            raise ValueError("Une feuille ne peut pas contenir plus de 64 pages")
        _validate_non_negative("La marge", self.margin_points)
        _validate_non_negative("L’espacement", self.gutter_points)
        _validate_usable_page(
            self.page_size,
            self.margin_points,
            self.gutter_points,
            self.rows,
            self.columns,
        )

    @property
    def page_size(self) -> tuple[float, float]:
        return resolve_page_size(self.page_format, self.orientation)

    @property
    def pages_per_sheet(self) -> int:
        return self.rows * self.columns


class LayoutService:
    """Create new laid-out PDFs while keeping the input PDF untouched."""

    def apply_target_format(
        self,
        source: Path,
        destination: Path,
        options: TargetFormatOptions | None = None,
    ) -> Path:
        selected = options or TargetFormatOptions()
        _require_pdf(source)
        width, height = selected.page_size
        target_rect = pikepdf.Rectangle(
            selected.margin_points,
            selected.margin_points,
            width - selected.margin_points,
            height - selected.margin_points,
        )
        with pikepdf.open(source) as input_pdf, pikepdf.Pdf.new() as output_pdf:
            if not input_pdf.pages:
                raise ValueError("Le PDF ne contient aucune page")
            for source_page in input_pdf.pages:
                target_page = output_pdf.add_blank_page(page_size=selected.page_size)
                overlay = output_pdf.copy_foreign(source_page.as_form_xobject())
                target_page.add_overlay(
                    overlay,
                    target_rect,
                    shrink=True,
                    expand=selected.allow_upscale,
                )  # type: ignore[call-arg]  # pikepdf 10 stubs omit supported keywords
            with atomic_file(destination, (source,)) as temporary:
                output_pdf.save(temporary)
        return destination

    def n_up(
        self,
        source: Path,
        destination: Path,
        options: NUpOptions | None = None,
    ) -> Path:
        selected = options or NUpOptions()
        _require_pdf(source)
        with pikepdf.open(source) as input_pdf, pikepdf.Pdf.new() as output_pdf:
            if not input_pdf.pages:
                raise ValueError("Le PDF ne contient aucune page")
            target_page: pikepdf.Page | None = None
            for page_index, source_page in enumerate(input_pdf.pages):
                slot = page_index % selected.pages_per_sheet
                if slot == 0:
                    target_page = output_pdf.add_blank_page(page_size=selected.page_size)
                if target_page is None:  # Defensive guard for static type checkers.
                    raise RuntimeError("La feuille de destination n’a pas été créée")
                overlay = output_pdf.copy_foreign(source_page.as_form_xobject())
                target_page.add_overlay(
                    overlay,
                    _slot_rectangle(slot, selected),
                    shrink=True,
                    expand=selected.allow_upscale,
                )  # type: ignore[call-arg]  # pikepdf 10 stubs omit supported keywords
            with atomic_file(destination, (source,)) as temporary:
                output_pdf.save(temporary)
        return destination


def resolve_page_size(
    page_format: PageFormat,
    orientation: PageOrientation,
) -> tuple[float, float]:
    width, height = PAGE_SIZES[page_format]
    return (height, width) if orientation is PageOrientation.LANDSCAPE else (width, height)


def _slot_rectangle(slot: int, options: NUpOptions) -> pikepdf.Rectangle:
    width, height = options.page_size
    usable_width = (
        width - (2 * options.margin_points) - ((options.columns - 1) * options.gutter_points)
    )
    usable_height = (
        height - (2 * options.margin_points) - ((options.rows - 1) * options.gutter_points)
    )
    cell_width = usable_width / options.columns
    cell_height = usable_height / options.rows
    row, column = divmod(slot, options.columns)
    left = options.margin_points + column * (cell_width + options.gutter_points)
    top = height - options.margin_points - row * (cell_height + options.gutter_points)
    return pikepdf.Rectangle(left, top - cell_height, left + cell_width, top)


def _validate_non_negative(label: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{label} ne peut pas être négative")


def _validate_usable_page(
    page_size: tuple[float, float],
    margin: float,
    gutter: float,
    rows: int,
    columns: int,
) -> None:
    width, height = page_size
    usable_width = width - (2 * margin) - ((columns - 1) * gutter)
    usable_height = height - (2 * margin) - ((rows - 1) * gutter)
    if usable_width <= 0 or usable_height <= 0:
        raise ValueError("Les marges et espacements ne laissent aucune zone imprimable")


def _require_pdf(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
