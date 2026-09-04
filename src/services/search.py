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
    pico_population: str = ""
    pico_intervention: str = ""
    pico_comparator: str = ""
    pico_outcome: str = ""
    inclusion_criteria: str = ""
    exclusion_criteria: str = ""


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
    pico_population: str = ""
    pico_intervention: str = ""
    pico_comparator: str = ""
    pico_outcome: str = ""
    inclusion_criteria: str = ""
    exclusion_criteria: str = ""
    source_type: str = "pubmed_search"
    parent_search_id: str | None = None
    translated_wos: str | None = None
    translated_ebsco: str | None = None
    suggested_query: str | None = None
    query_suggestion_blocks: list[dict] | None = None
    study_types: list[str] | None = None
    ctgov_query: str | None = None
    ctgov_hits: list[dict] | None = None
    pico_ai_used: bool = False
    pico_ai_model: str | None = None
    pico_ai_prompt_version: str | None = None
    pico_ai_source_text: str | None = None
    pico_ai_draft: dict | None = None
    pico_ai_accepted: dict | None = None


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
        pico_population=params.pico_population,
        pico_intervention=params.pico_intervention,
        pico_comparator=params.pico_comparator,
        pico_outcome=params.pico_outcome,
        inclusion_criteria=params.inclusion_criteria,
        exclusion_criteria=params.exclusion_criteria,
    )


def merge_living_search(
    previous: SearchResult,
    fresh: SearchResult,
) -> SearchResult:
    """Living Search：保留已有 PMID 的初筛决策，新 PMID 标为未筛。"""
    prior_by_pmid = {record.pmid: record for record in previous.records}
    merged_records: list[EvidenceRecord] = []
    for record in fresh.records:
        old = prior_by_pmid.get(record.pmid)
        if old is None:
            merged_records.append(record.model_copy(deep=True))
            continue
        merged_records.append(
            record.model_copy(
                update={
                    "screening_status": old.screening_status,
                    "reviewer2_status": old.reviewer2_status,
                    "exclusion_reason": old.exclusion_reason,
                    "notes": old.notes,
                    "screening_history": [h.model_copy(deep=True) for h in old.screening_history],
                    "potential_duplicate": old.potential_duplicate,
                    "extraction": old.extraction.model_copy() if old.extraction else None,
                }
            )
        )
    fresh.records = merged_records
    fresh.parent_search_id = previous.search_id
    fresh.research_question = previous.research_question or fresh.research_question
    fresh.pico_population = previous.pico_population or fresh.pico_population
    fresh.pico_intervention = previous.pico_intervention or fresh.pico_intervention
    fresh.pico_comparator = previous.pico_comparator or fresh.pico_comparator
    fresh.pico_outcome = previous.pico_outcome or fresh.pico_outcome
    fresh.inclusion_criteria = previous.inclusion_criteria or fresh.inclusion_criteria
    fresh.exclusion_criteria = previous.exclusion_criteria or fresh.exclusion_criteria
    fresh.translated_wos = fresh.translated_wos or previous.translated_wos
    fresh.translated_ebsco = fresh.translated_ebsco or previous.translated_ebsco
    fresh.suggested_query = fresh.suggested_query or previous.suggested_query
    fresh.query_suggestion_blocks = (
        fresh.query_suggestion_blocks or previous.query_suggestion_blocks
    )
    fresh.study_types = fresh.study_types or previous.study_types
    fresh.ctgov_query = fresh.ctgov_query or previous.ctgov_query
    fresh.ctgov_hits = fresh.ctgov_hits or previous.ctgov_hits
    if not fresh.pico_ai_used and previous.pico_ai_used:
        fresh.pico_ai_used = previous.pico_ai_used
        fresh.pico_ai_model = previous.pico_ai_model
        fresh.pico_ai_prompt_version = previous.pico_ai_prompt_version
        fresh.pico_ai_source_text = previous.pico_ai_source_text
        fresh.pico_ai_draft = previous.pico_ai_draft
        fresh.pico_ai_accepted = previous.pico_ai_accepted
    return fresh


def create_import_result(
    records: list[EvidenceRecord],
    *,
    research_question: str = "",
    query_label: str = "（导入记录，无 PubMed 检索式）",
    source_type: str = "import",
    pico_population: str = "",
    pico_intervention: str = "",
    pico_comparator: str = "",
    pico_outcome: str = "",
    inclusion_criteria: str = "",
    exclusion_criteria: str = "",
) -> SearchResult:
    """为导入记录创建 SearchResult。"""
    return SearchResult(
        search_id=uuid4().hex[:8],
        research_question=research_question,
        query=query_label,
        year_from=None,
        year_to=None,
        retmax=len(records),
        total_hits=len(records),
        records=records,
        executed_at=datetime.now(timezone.utc),
        source_type=source_type,
        pico_population=pico_population,
        pico_intervention=pico_intervention,
        pico_comparator=pico_comparator,
        pico_outcome=pico_outcome,
        inclusion_criteria=inclusion_criteria,
        exclusion_criteria=exclusion_criteria,
    )
