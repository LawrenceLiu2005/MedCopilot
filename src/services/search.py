"""搜索业务逻辑。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.clients.pubmed import PubMedClient
from src.models.evidence import EvidenceRecord


@dataclass
class PmidDiff:
    """两次检索 PMID 对比结果。"""

    only_in_first: list[str]
    only_in_second: list[str]
    in_both: list[str]

    @property
    def added_count(self) -> int:
        """第二次相对第一次新增的 PMID 数。"""
        return len(self.only_in_second)

    @property
    def removed_count(self) -> int:
        """第二次相对第一次消失的 PMID 数。"""
        return len(self.only_in_first)

    @property
    def common_count(self) -> int:
        return len(self.in_both)

ALLOWED_RETMAX = (10, 20, 50, 100, 200, 500)
MAX_RETMAX = 500


@dataclass
class SearchParams:
    """搜索参数。"""

    research_question: str
    query: str
    year_from: int | None
    year_to: int | None
    retmax: int
    sort: str | None = None


@dataclass
class SearchResult:
    """单次搜索结果。"""

    search_id: str
    research_question: str
    query: str
    year_from: int | None
    year_to: int | None
    retmax: int
    total_hits: int
    records: list[EvidenceRecord]
    executed_at: datetime
    sort: str | None = None
    missing_pmids: list[str] | None = None
    dedupe_removed_pmids: list[str] | None = None
    raw_query: str | None = None
    author_wrap_applied: bool = False


def pmids_from_search(search: SearchResult) -> set[str]:
    """提取一次检索已拉回文献的 PMID 集合。"""
    return {record.pmid for record in search.records}


def compare_search_pmids(first: SearchResult, second: SearchResult) -> PmidDiff:
    """对比两次检索已拉回的 PMID（新增 / 消失 / 共有）。"""
    set_a = pmids_from_search(first)
    set_b = pmids_from_search(second)
    only_first = sorted(set_a - set_b, key=int)
    only_second = sorted(set_b - set_a, key=int)
    in_both = sorted(set_a & set_b, key=int)
    return PmidDiff(
        only_in_first=only_first,
        only_in_second=only_second,
        in_both=in_both,
    )


def attempted_retrieved_count(search: SearchResult, listed: int | None = None) -> int:
    """已尝试拉回的 PMID 数（列表 + 去重移除 + 元数据失败），不含「超出条数上限未请求」的命中。"""
    listed_n = listed if listed is not None else len(search.records)
    return (
        listed_n
        + len(search.dedupe_removed_pmids or [])
        + len(search.missing_pmids or [])
    )


def year_bounds(year_from: int | None, year_to: int | None) -> tuple[str | None, str | None]:
    """年份转 ESearch mindate/maxdate；不修改检索式本身。"""
    mindate = str(year_from) if year_from is not None else None
    maxdate = str(year_to) if year_to is not None else None
    return mindate, maxdate


def run_search(params: SearchParams, client: PubMedClient | None = None) -> SearchResult:
    """执行 PubMed 搜索。"""
    if params.retmax not in ALLOWED_RETMAX:
        raise ValueError(f"返回条数必须是 {ALLOWED_RETMAX} 之一。")
    if (
        params.year_from is not None
        and params.year_to is not None
        and params.year_from > params.year_to
    ):
        raise ValueError("年份起不能大于年份止。")

    pubmed = client or PubMedClient()
    mindate, maxdate = year_bounds(params.year_from, params.year_to)
    total_hits, records, missing_pmids = pubmed.search(
        params.query,
        retmax=params.retmax,
        mindate=mindate,
        maxdate=maxdate,
        sort=params.sort,
    )
    return SearchResult(
        search_id=uuid4().hex[:8],
        research_question=params.research_question,
        query=params.query,
        year_from=params.year_from,
        year_to=params.year_to,
        retmax=params.retmax,
        sort=params.sort,
        total_hits=total_hits,
        records=records,
        executed_at=datetime.now(timezone.utc),
        missing_pmids=missing_pmids or None,
    )
