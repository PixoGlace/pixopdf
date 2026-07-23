from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SourceDocument:
    path: Path
    page_count: int
    display_name: str
    id: UUID

    @classmethod
    def create(cls, path: Path, page_count: int) -> "SourceDocument":
        return cls(path.resolve(), page_count, path.name, uuid4())
