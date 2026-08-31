"""检索式辅助测试。"""

import pytest

from src.services.query_builder import (
    author_wrap_applied,
    build_effective_query,
    can_wrap_author_field,
    has_pubmed_syntax,
    wrap_author_query,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ('"diabetes"[MeSH]', True),
        ("metformin[Title/Abstract]", True),
        ('"Smith"[Author]', True),
        ("A AND B", True),
        ("x OR y", True),
        ("heart failure", False),
        ("ng cheng han", False),
        ("", False),
    ],
)
def test_has_pubmed_syntax(query: str, expected: bool):
    assert has_pubmed_syntax(query) is expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("ng cheng han", True),
        ("Smith J", True),
        ("heart failure", True),
        ("breast cancer", True),
        ('"diabetes"[MeSH]', False),
        ("metformin[Title/Abstract]", False),
        ("A AND B", False),
        ('"Smith"[Author]', False),
        ("", False),
    ],
)
def test_can_wrap_author_field(query: str, expected: bool):
    assert can_wrap_author_field(query) is expected


def test_wrap_author_query():
    assert wrap_author_query("ng cheng han") == '"ng cheng han"[Author]'
    assert wrap_author_query("  ng   cheng han  ") == '"ng cheng han"[Author]'


@pytest.mark.parametrize(
    ("raw", "author_field", "expected"),
    [
        ("ng cheng han", False, "ng cheng han"),
        ("ng cheng han", True, '"ng cheng han"[Author]'),
        ("heart failure", True, '"heart failure"[Author]'),
        ('"diabetes"[MeSH] AND metformin[Title/Abstract]', True, '"diabetes"[MeSH] AND metformin[Title/Abstract]'),
        ("A AND B", True, "A AND B"),
    ],
)
def test_build_effective_query(raw: str, author_field: bool, expected: str):
    assert build_effective_query(raw, author_field=author_field) == expected


def test_author_wrap_applied():
    assert author_wrap_applied("ng cheng han", author_field=True) is True
    assert author_wrap_applied("ng cheng han", author_field=False) is False
    assert author_wrap_applied('"diabetes"[MeSH]', author_field=True) is False
