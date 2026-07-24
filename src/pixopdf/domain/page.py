from dataclasses import dataclass, replace
from enum import IntFlag, auto
from uuid import UUID, uuid4


class PageChange(IntFlag):
    """Persistent visual changes applied to a page in the current project."""

    NONE = 0
    MOVED = auto()
    MODIFIED = auto()
    ADDED = auto()
    DELETED = auto()


@dataclass(frozen=True, slots=True)
class PageReference:
    source_document_id: UUID | None
    source_page_index: int | None
    id: UUID
    rotation: int = 0
    crop_box: tuple[float, float, float, float] | None = None
    blank_size: tuple[float, float] | None = None
    stable_number: int = 0
    changes: PageChange = PageChange.NONE

    @classmethod
    def create(
        cls,
        document_id: UUID,
        index: int,
        stable_number: int = 0,
    ) -> "PageReference":
        return cls(document_id, index, uuid4(), stable_number=stable_number)

    @classmethod
    def blank(
        cls,
        width: float = 595.28,
        height: float = 841.89,
        stable_number: int = 0,
    ) -> "PageReference":
        """Create a virtual blank A4 page measured in PDF points."""
        return cls(
            None,
            None,
            uuid4(),
            blank_size=(width, height),
            stable_number=stable_number,
            changes=PageChange.ADDED,
        )

    @property
    def is_blank(self) -> bool:
        return self.source_document_id is None

    @property
    def is_deleted(self) -> bool:
        return bool(self.changes & PageChange.DELETED)

    def rotated(self, degrees: int) -> "PageReference":
        if degrees % 90:
            raise ValueError("Rotation must be a multiple of 90 degrees")
        rotation = (self.rotation + degrees) % 360
        changes = self.changes
        if rotation or self.crop_box is not None:
            changes |= PageChange.MODIFIED
        else:
            changes &= ~PageChange.MODIFIED
        return replace(self, rotation=rotation, changes=changes)

    def duplicate(self, stable_number: int = 0) -> "PageReference":
        return replace(
            self,
            id=uuid4(),
            stable_number=stable_number,
            changes=PageChange.ADDED,
        )
