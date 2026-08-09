import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path


class OutputPathError(ValueError):
    """Raised when an operation would overwrite one of its source files."""


def ensure_distinct_paths(source: Path, destination: Path) -> None:
    """Reject in-place PDF transformations so source documents stay untouched."""
    if source.resolve() == destination.resolve():
        raise OutputPathError("Le fichier de sortie doit être différent du fichier source")


def ensure_distinct_destination(destination: Path, sources: Sequence[Path]) -> None:
    """Reject an output path that points at any immutable input."""
    if any(source.resolve() == destination.resolve() for source in sources):
        raise OutputPathError("Le fichier de sortie doit être différent des fichiers sources")


@contextmanager
def atomic_output_path(destination: Path, *, suffix: str = ".pdf") -> Iterator[Path]:
    """Yield a sibling temporary path and atomically publish it on success."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=suffix,
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        yield temporary
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def atomic_file(destination: Path, sources: Sequence[Path] = ()) -> Iterator[Path]:
    """Yield an adjacent temporary path and atomically publish it on success."""
    ensure_distinct_destination(destination, sources)
    with atomic_output_path(destination, suffix=".tmp") as temporary:
        yield temporary


@contextmanager
def staging_directory(destination: Path) -> Iterator[Path]:
    """Yield a temporary sibling directory for a multi-file operation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}-",
        dir=destination.parent,
    ) as temporary_name:
        yield Path(temporary_name)


def publish_staged_files(
    staging: Path,
    destination: Path,
    relative_names: Sequence[Path],
) -> list[Path]:
    """Publish a staged batch without overwriting existing outputs."""
    if not relative_names:
        return []
    if destination.exists() and not destination.is_dir():
        raise NotADirectoryError(destination)

    outputs = [destination / relative_name for relative_name in relative_names]
    collisions = [output for output in outputs if output.exists()]
    if collisions:
        names = ", ".join(path.name for path in collisions[:3])
        raise FileExistsError(f"Les fichiers de destination existent déjà : {names}")

    destination_created = not destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    try:
        for relative_name, output in zip(relative_names, outputs, strict=True):
            output.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative_name, output)
            published.append(output)
    except BaseException:
        for output in published:
            output.unlink(missing_ok=True)
        if destination_created:
            with suppress(OSError):
                destination.rmdir()
        raise
    return outputs
