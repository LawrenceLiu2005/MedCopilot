"""Living Search 测试。"""

from datetime import datetime, timezone

from src.models.evidence import EvidenceRecord, ExtractionData, ScreeningStatus
from src.services.search import SearchResult, merge_living_search


def _record(pmid: str, status: ScreeningStatus = ScreeningStatus.UNSCREENED) -> EvidenceRecord:
    return EvidenceRecord(
        pmid=pmid,
        title=f"Title {pmid}",
        screening_status=status,
        reviewer2_status=ScreeningStatus.INCLUDE if pmid == "2" else None,
        exclusion_reason="Wrong population" if status == ScreeningStatus.EXCLUDE else None,
        extraction=ExtractionData(e1=3, n1=10, e2=1, n2=10) if pmid == "2" else None,
    )


def test_merge_living_search_preserves_decisions():
    previous = SearchResult(
        search_id="old1",
        research_question="Q",
        query="diabetes",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=2,
        records=[_record("1", ScreeningStatus.INCLUDE), _record("2", ScreeningStatus.EXCLUDE)],
        executed_at=datetime.now(timezone.utc),
        suggested_query="suggested",
        pico_ai_used=True,
        pico_ai_model="deepseek-v4-flash",
        pico_ai_source_text="白话",
    )
    fresh = SearchResult(
        search_id="new1",
        research_question="Q",
        query="diabetes",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=3,
        records=[_record("2"), _record("3")],
        executed_at=datetime.now(timezone.utc),
    )
    merged = merge_living_search(previous, fresh)
    by_pmid = {r.pmid: r for r in merged.records}
    assert by_pmid["2"].screening_status == ScreeningStatus.EXCLUDE
    assert by_pmid["2"].reviewer2_status == ScreeningStatus.INCLUDE
    assert by_pmid["2"].extraction is not None
    assert by_pmid["2"].extraction.e1 == 3
    assert by_pmid["3"].screening_status == ScreeningStatus.UNSCREENED
    assert by_pmid["3"].reviewer2_status is None
    assert by_pmid["3"].extraction is None
    assert merged.parent_search_id == "old1"
    assert merged.suggested_query == "suggested"
    assert merged.pico_ai_used is True
    assert merged.pico_ai_model == "deepseek-v4-flash"
    assert merged.pico_ai_source_text == "白话"
