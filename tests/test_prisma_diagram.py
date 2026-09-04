"""PRISMA 流程图测试。"""

from datetime import datetime, timezone

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.prisma_diagram import prisma_to_svg
from src.services.search import SearchResult


def test_prisma_to_svg():
    search = SearchResult(
        search_id="abc",
        research_question="",
        query="test",
        year_from=None,
        year_to=None,
        retmax=3,
        total_hits=3,
        records=[
            EvidenceRecord(pmid="1", title="A", screening_status=ScreeningStatus.INCLUDE),
            EvidenceRecord(pmid="2", title="B", screening_status=ScreeningStatus.EXCLUDE),
            EvidenceRecord(pmid="3", title="C", screening_status=ScreeningStatus.UNSCREENED),
        ],
        executed_at=datetime.now(timezone.utc),
    )
    svg = prisma_to_svg(search)
    assert "<svg" in svg.lower()
