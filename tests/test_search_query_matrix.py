"""搜索 query 透传矩阵测试（mock PubMed，不依赖网络）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models.evidence import EvidenceRecord
from src.services.query_builder import build_effective_query
from src.services.search import SearchParams, run_search

QUERY_CASES = [
    ('(diabetes mellitus, type 2[MeSH]) AND metformin[Title/Abstract]', False),
    ('"hypertension"[Title] AND "2020"[Date - Publication]', False),
    ("CRISPR[Title/Abstract]", False),
    ('"Smith"[Author]', False),
    ("ng cheng han", True),
    ("heart failure", False),
]


@pytest.mark.parametrize(("query", "author_field"), QUERY_CASES)
def test_run_search_passes_confirmed_query_unchanged_when_no_wrap(query: str, author_field: bool):
    client = MagicMock()
    client.search.return_value = (10, [EvidenceRecord(pmid="1", title="Test")], [])
    effective = build_effective_query(query, author_field=author_field)

    result = run_search(
        SearchParams(
            research_question="矩阵测试",
            query=effective,
            year_from=2020,
            year_to=2024,
            retmax=10,
            sort=None,
        ),
        client=client,
    )

    client.search.assert_called_once_with(
        effective,
        retmax=10,
        mindate="2020",
        maxdate="2024",
        sort=None,
    )
    assert result.query == effective


def test_author_field_wrap_only_when_compatible():
    client = MagicMock()
    client.search.return_value = (5, [EvidenceRecord(pmid="1", title="Test")], [])

    plain = "ng cheng han"
    wrapped = build_effective_query(plain, author_field=True)
    assert wrapped == '"ng cheng han"[Author]'

    run_search(
        SearchParams(
            research_question="作者",
            query=wrapped,
            year_from=None,
            year_to=None,
            retmax=10,
        ),
        client=client,
    )
    client.search.assert_called_with(
        '"ng cheng han"[Author]',
        retmax=10,
        mindate=None,
        maxdate=None,
        sort=None,
    )

    client.reset_mock()
    mesh_query = '"diabetes"[MeSH] AND metformin[Title/Abstract]'
    unchanged = build_effective_query(mesh_query, author_field=True)
    assert unchanged == mesh_query

    run_search(
        SearchParams(
            research_question="主题",
            query=unchanged,
            year_from=None,
            year_to=None,
            retmax=10,
        ),
        client=client,
    )
    client.search.assert_called_with(
        mesh_query,
        retmax=10,
        mindate=None,
        maxdate=None,
        sort=None,
    )
