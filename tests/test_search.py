"""搜索服务测试。"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.models.evidence import EvidenceRecord
from src.services.search import (
    SearchParams,
    SearchResult,
    attempted_retrieved_count,
    compare_search_pmids,
    run_search,
    year_bounds,
)


def test_year_bounds():
    assert year_bounds(2020, 2024) == ("2020", "2024")
    assert year_bounds(None, 2024) == (None, "2024")
    assert year_bounds(2020, None) == ("2020", None)
    assert year_bounds(None, None) == (None, None)


def test_run_search_passes_year_filters_without_modifying_query():
    client = MagicMock()
    client.search.return_value = (100, [EvidenceRecord(pmid="1", title="Test")], [])
    params = SearchParams(
        research_question="RQ",
        query='"diabetes"[Title]',
        year_from=2020,
        year_to=2024,
        retmax=10,
    )
    result = run_search(params, client=client)
    client.search.assert_called_once_with(
        '"diabetes"[Title]',
        retmax=10,
        mindate="2020",
        maxdate="2024",
        sort=None,
    )
    assert result.query == '"diabetes"[Title]'
    assert result.total_hits == 100
    assert len(result.records) == 1
    assert result.search_id


def test_run_search_rejects_inverted_year_range():
    client = MagicMock()
    params = SearchParams(
        research_question="RQ",
        query="diabetes",
        year_from=2024,
        year_to=2020,
        retmax=10,
    )
    with pytest.raises(ValueError, match="年份起不能大于年份止"):
        run_search(params, client=client)
    client.search.assert_not_called()


def test_attempted_retrieved_count_excludes_dedupe_from_unfetched():
    result = run_search(
        SearchParams(
            research_question="RQ",
            query="q",
            year_from=None,
            year_to=None,
            retmax=10,
        ),
        client=MagicMock(
            search=MagicMock(return_value=(100, [EvidenceRecord(pmid="1", title="T")], ["9"]))
        ),
    )
    result.dedupe_removed_pmids = ["2"]
    # 列表 1 + 去重 1 + 元数据失败 1 = 已尝试 3，未拉回应是 100-3
    assert attempted_retrieved_count(result) == 3


def test_compare_search_pmids():
    first = SearchResult(
        search_id="a",
        research_question="",
        query="q1",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=3,
        records=[
            EvidenceRecord(pmid="1", title="A"),
            EvidenceRecord(pmid="2", title="B"),
        ],
        executed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    second = SearchResult(
        search_id="b",
        research_question="",
        query="q2",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=3,
        records=[
            EvidenceRecord(pmid="2", title="B"),
            EvidenceRecord(pmid="3", title="C"),
        ],
        executed_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    diff = compare_search_pmids(first, second)
    assert diff.only_in_first == ["1"]
    assert diff.only_in_second == ["3"]
    assert diff.in_both == ["2"]
    assert diff.added_count == 1
    assert diff.removed_count == 1
    assert diff.common_count == 1
