from dataclasses import dataclass, field, replace
from uuid import UUID

from pixopdf.domain.page import PageChange, PageReference
from pixopdf.domain.project import PdfProject

from .base import Command


@dataclass
class DeletePagesCommand(Command):
    project: PdfProject
    indices: list[int]
    _removed: list[tuple[int, PageReference]] = field(default_factory=list, init=False)

    def execute(self) -> None:
        valid = sorted({index for index in self.indices if 0 <= index < len(self.project.pages)})
        self._removed = [(index, self.project.pages[index]) for index in valid]
        for index, _page in reversed(self._removed):
            del self.project.pages[index]
        if self._removed:
            self.project.modified = True

    def undo(self) -> None:
        for index, page in self._removed:
            self.project.pages.insert(index, page)
        if self._removed:
            self.project.modified = True


@dataclass
class RotatePagesCommand(Command):
    project: PdfProject
    indices: list[int]
    degrees: int
    _previous: list[tuple[int, PageReference]] = field(default_factory=list, init=False)

    def execute(self) -> None:
        valid = sorted({index for index in self.indices if 0 <= index < len(self.project.pages)})
        self._previous = [(index, self.project.pages[index]) for index in valid]
        for index, page in self._previous:
            self.project.pages[index] = page.rotated(self.degrees)
        if self._previous:
            self.project.modified = True

    def undo(self) -> None:
        for index, page in self._previous:
            if 0 <= index < len(self.project.pages):
                self.project.pages[index] = page
        if self._previous:
            self.project.modified = True


@dataclass
class DuplicatePagesCommand(Command):
    project: PdfProject
    indices: list[int]
    _inserted: list[int] = field(default_factory=list, init=False)
    _pages: list[PageReference] = field(default_factory=list, init=False)

    @property
    def inserted_page_ids(self) -> list[UUID]:
        return [page.id for page in self._pages]

    def execute(self) -> None:
        self._inserted.clear()
        valid = sorted({index for index in self.indices if 0 <= index < len(self.project.pages)})
        if not self._pages:
            self._pages = [
                self.project.pages[index].duplicate(self.project.allocate_stable_number())
                for index in valid
            ]
        for offset, (index, page) in enumerate(zip(valid, self._pages, strict=True)):
            source_index = index + offset
            insertion_index = source_index + 1
            self.project.pages.insert(insertion_index, page)
            self._inserted.append(insertion_index)
        if self._inserted:
            self.project.modified = True

    def undo(self) -> None:
        for index in reversed(self._inserted):
            del self.project.pages[index]
        if self._inserted:
            self.project.modified = True


@dataclass
class MovePagesCommand(Command):
    project: PdfProject
    source: int
    destination: int
    _previous: list[PageReference] = field(default_factory=list, init=False)

    def execute(self) -> None:
        if not 0 <= self.source < len(self.project.pages):
            raise IndexError("Source page index is out of range")
        if not 0 <= self.destination <= len(self.project.pages):
            raise IndexError("Destination page index is out of range")
        self._previous = list(self.project.pages)
        if self.source == self.destination:
            return
        page = self.project.pages.pop(self.source)
        page = replace(page, changes=page.changes | PageChange.MOVED)
        self.project.pages.insert(self.destination, page)
        self.project.modified = True

    def undo(self) -> None:
        if self._previous:
            self.project.pages[:] = self._previous
            self.project.modified = True


@dataclass
class InsertBlankPageCommand(Command):
    project: PdfProject
    index: int
    count: int = 1
    page_size: tuple[float, float] = (595.28, 841.89)
    _pages: list[PageReference] = field(default_factory=list, init=False)

    @property
    def inserted_page_ids(self) -> list[UUID]:
        return [page.id for page in self._pages]

    def execute(self) -> None:
        insertion_index = max(0, min(self.index, len(self.project.pages)))
        if not self._pages:
            self._pages = [
                PageReference.blank(
                    *self.page_size,
                    stable_number=self.project.allocate_stable_number(),
                )
                for _ in range(self.count)
            ]
        for offset, page in enumerate(self._pages):
            self.project.pages.insert(insertion_index + offset, page)
        if self._pages:
            self.project.modified = True

    def undo(self) -> None:
        inserted_ids = {page.id for page in self._pages}
        self.project.pages[:] = [page for page in self.project.pages if page.id not in inserted_ids]
        if self._pages:
            self.project.modified = True


@dataclass
class ReorderPagesCommand(Command):
    """Apply an ordering emitted by the page grid while preserving undo."""

    project: PdfProject
    ordered_ids: list[UUID]
    moved_ids: set[UUID] | None = None
    _previous: list[PageReference] = field(default_factory=list, init=False)

    def execute(self) -> None:
        pages_by_id = {page.id: page for page in self.project.pages}
        if (
            len(self.ordered_ids) != len(self.project.pages)
            or len(set(self.ordered_ids)) != len(self.ordered_ids)
            or set(self.ordered_ids) != set(pages_by_id)
        ):
            raise ValueError("The reordered page list does not match the project")
        if self.moved_ids is None:
            previous_positions = {
                page.id: position for position, page in enumerate(self.project.pages)
            }
            moved_ids = {
                page_id
                for position, page_id in enumerate(self.ordered_ids)
                if previous_positions[page_id] != position
            }
        else:
            moved_ids = set(self.moved_ids)
            if not moved_ids <= set(pages_by_id):
                raise ValueError("The moved page list does not match the project")

        self._previous = list(self.project.pages)
        self.project.pages[:] = [
            replace(page, changes=page.changes | PageChange.MOVED) if page.id in moved_ids else page
            for page in (pages_by_id[page_id] for page_id in self.ordered_ids)
        ]
        self.project.modified = True

    def undo(self) -> None:
        self.project.pages[:] = self._previous
        self.project.modified = True
