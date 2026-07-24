from dataclasses import dataclass, field
from uuid import UUID

from pixopdf.domain.document import SourceDocument
from pixopdf.domain.page import PageReference
from pixopdf.domain.project import PdfProject

from .base import Command


@dataclass
class ClearWorkspaceCommand(Command):
    """Remove every document and page while keeping an undoable snapshot."""

    project: PdfProject
    _documents: dict[UUID, SourceDocument] = field(default_factory=dict, init=False)
    _pages: list[PageReference] = field(default_factory=list, init=False)
    _previous_modified: bool = field(default=False, init=False)

    @property
    def removed_document_count(self) -> int:
        return len(self._documents)

    @property
    def removed_page_count(self) -> int:
        return len(self._pages)

    def execute(self) -> None:
        self._documents = dict(self.project.documents)
        self._pages = list(self.project.pages)
        self._previous_modified = self.project.modified
        self.project.documents.clear()
        self.project.pages.clear()
        self.project.modified = True

    def undo(self) -> None:
        self.project.documents = dict(self._documents)
        self.project.pages = list(self._pages)
        self.project.modified = self._previous_modified


@dataclass
class RemoveDocumentCommand(Command):
    """Remove one source and all its page references without touching its file."""

    project: PdfProject
    document_id: UUID
    _document: SourceDocument | None = field(default=None, init=False)
    _document_position: int = field(default=0, init=False)
    _removed_pages: list[tuple[int, PageReference]] = field(default_factory=list, init=False)

    @property
    def removed_page_count(self) -> int:
        return len(self._removed_pages)

    def execute(self) -> None:
        document = self.project.documents.get(self.document_id)
        if document is None:
            self._document = None
            self._removed_pages = []
            return
        document_ids = list(self.project.documents)
        self._document = document
        self._document_position = document_ids.index(self.document_id)
        self._removed_pages = [
            (index, page)
            for index, page in enumerate(self.project.pages)
            if page.source_document_id == self.document_id
        ]
        del self.project.documents[self.document_id]
        self.project.pages[:] = [
            page for page in self.project.pages if page.source_document_id != self.document_id
        ]
        self.project.modified = True

    def undo(self) -> None:
        if self._document is None:
            return
        documents = list(self.project.documents.items())
        insertion_index = max(0, min(self._document_position, len(documents)))
        documents.insert(insertion_index, (self.document_id, self._document))
        self.project.documents = dict(documents)
        for index, page in self._removed_pages:
            self.project.pages.insert(index, page)
        self.project.modified = True
