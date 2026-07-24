from enum import StrEnum

from pixopdf.domain.page_selection import parse_page_ranges


class SplitStrategy(StrEnum):
    EACH_PAGE = "each_page"
    BATCH = "batch"
    RANGES = "ranges"


def build_split_groups(
    page_count: int,
    strategy: SplitStrategy | str,
    *,
    batch_size: int = 1,
    ranges: str = "",
) -> list[list[int]]:
    """Build zero-based page groups for a split operation."""
    if page_count < 1:
        raise ValueError("Aucune page active à diviser")
    selected_strategy = strategy if isinstance(strategy, SplitStrategy) else SplitStrategy(strategy)
    if selected_strategy is SplitStrategy.EACH_PAGE:
        return [[index] for index in range(page_count)]
    if selected_strategy is SplitStrategy.BATCH:
        if batch_size < 1:
            raise ValueError("Le nombre de pages par lot doit être supérieur à zéro")
        return [
            list(range(start, min(start + batch_size, page_count)))
            for start in range(0, page_count, batch_size)
        ]

    raw_groups = [group.strip() for group in ranges.split(";")]
    if not ranges.strip() or any(not group for group in raw_groups):
        raise ValueError("Saisissez des plages séparées par un point-virgule")
    groups = [
        [page_number - 1 for page_number in parse_page_ranges(group, page_count)]
        for group in raw_groups
    ]
    if any(not group for group in groups):
        raise ValueError("Chaque plage doit contenir au moins une page")
    return groups
