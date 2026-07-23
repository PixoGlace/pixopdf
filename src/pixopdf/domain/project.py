from dataclasses import dataclass, field, replace
from uuid import UUID

from .document import SourceDocument
from .page import PageReference


@dataclass(slots=True)
class PdfProject:
    documents: dict[UUID, SourceDocument] = field(default_factory=dict)
    pages: list[PageReference] = field(default_factory=list)
    modified: bool = False
    _next_stable_number: int = field(default=1, init=False, repr=False)

    def __post_init__(self) -> None:
        """Normalise projects reconstructed from an existing page snapshot."""
        self._next_stable_number = (
            max(
                (page.stable_number for page in self.pages if page.stable_number > 0),
                default=0,
            )
            + 1
        )
        self.ensure_page_numbers()

    def ensure_page_numbers(self) -> None:
        """Assign a unique stable number to unnumbered or conflicting pages.

        This also supports clients that append ``PageReference`` instances directly
        instead of going through the project commands.
        """
        highest_existing = max(
            (page.stable_number for page in self.pages if page.stable_number > 0),
            default=0,
        )
        self._next_stable_number = max(self._next_stable_number, highest_existing + 1)
        seen: set[int] = set()
        for index, page in enumerate(self.pages):
            if page.stable_number > 0 and page.stable_number not in seen:
                seen.add(page.stable_number)
                continue
            stable_number = self.allocate_stable_number()
            self.pages[index] = replace(page, stable_number=stable_number)
            seen.add(stable_number)

    def allocate_stable_number(self) -> int:
        """Return a page number that is never reused during this project session."""
        highest_existing = max((page.stable_number for page in self.pages), default=0)
        self._next_stable_number = max(self._next_stable_number, highest_existing + 1)
        number = self._next_stable_number
        self._next_stable_number += 1
        return number

    def add_document(self, document: SourceDocument) -> None:
        if document.id in self.documents:
            return
        self.documents[document.id] = document
        self.pages.extend(
            PageReference.create(
                document.id,
                index,
                stable_number=self.allocate_stable_number(),
            )
            for index in range(document.page_count)
        )
        self.modified = True

    def source_for(self, page: PageReference) -> SourceDocument:
        if page.source_document_id is None:
            raise ValueError("A blank page has no source document")
        return self.documents[page.source_document_id]
