import pytest

from pixopdf.domain.page_selection import parse_page_ranges


def test_range_parser() -> None:
    assert parse_page_ranges("1-3, 7, 10-12") == [1, 2, 3, 7, 10, 11, 12]


def test_range_parser_rejects_zero() -> None:
    with pytest.raises(ValueError):
        parse_page_ranges("0")


def test_range_parser_rejects_out_of_bounds_page() -> None:
    with pytest.raises(ValueError, match="dépasse"):
        parse_page_ranges("1-8", page_count=7)
