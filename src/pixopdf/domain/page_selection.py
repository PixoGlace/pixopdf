def parse_page_ranges(value: str, page_count: int | None = None) -> list[int]:
    """Parse a one-based expression such as ``1-3, 7`` into sorted page numbers."""
    if not value.strip():
        return []
    pages: set[int] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError("Un intervalle de pages est vide")
        raw_bounds = part.split("-")
        if len(raw_bounds) > 2:
            raise ValueError(f"Intervalle invalide : {part}")
        try:
            bounds = [int(bound.strip()) for bound in raw_bounds]
        except ValueError as exc:
            raise ValueError(f"Numéro de page invalide : {part}") from exc
        start, end = bounds[0], bounds[-1]
        if start < 1 or end < 1 or end < start:
            raise ValueError(f"Intervalle invalide : {part}")
        if page_count is not None and end > page_count:
            raise ValueError(f"La page {end} dépasse les {page_count} pages du document")
        pages.update(range(start, end + 1))
    return sorted(pages)
