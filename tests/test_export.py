"""导出功能测试。"""

import json
from datetime import datetime, timezone

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.export import filter_records_for_export, to_audit_report_md, to_csv, to_ris, to_search_snapshot
from src.services.search import SearchResult


def test_to_ris_contains_pmid():
    records = [
        EvidenceRecord(
            pmid="123",
            title="Test Title",
            authors=["Zhang Wei"],
            journal="J Test",
            publication_year=2024,
            doi="10.1/test",
            abstract="Abs",
        )
    ]
    ris = to_ris(records)
    assert "AN  - 123" in ris
    assert "TI  - Test Title" in ris
    assert "DO  - 10.1/test" in ris


def test_to_csv_columns():
    records = [
        EvidenceRecord(
            pmid="123",
            title="Test",
            screening_status=ScreeningStatus.INCLUDE,
        )
    ]
    csv_text = to_csv(records)
    assert "PMID" in csv_text
    assert "Screening Status" in csv_text
    assert "123" in csv_text
    assert "Include" in csv_text


def test_search_snapshot_contains_query():
    search = SearchResult(
        search_id="abc123",
        research_question="RQ",
        query='"diabetes"[Title]',
        year_from=2020,
        year_to=2024,
        retmax=10,
        total_hits=100,
        records=[EvidenceRecord(pmid="1", title="T")],
        executed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    snapshot = json.loads(to_search_snapshot(search))
    assert snapshot["exact_query"] == '"diabetes"[Title]'
    assert snapshot["retrieved_pmids"] == ["1"]
    assert snapshot["total_hits"] == 100
    assert snapshot["retrieved_count"] == 1
    assert snapshot["missing_pmids"] == []
    assert snapshot["dedupe_removed_pmids"] == []
    assert snapshot["raw_query"] is None
    assert snapshot["author_wrap_applied"] is False


def test_search_snapshot_uses_passed_records_for_screening():
    search = SearchResult(
        search_id="abc123",
        research_question="RQ",
        query="q",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=2,
        records=[EvidenceRecord(pmid="1", title="T")],
        executed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        missing_pmids=["9"],
        dedupe_removed_pmids=["8"],
        raw_query="plain name",
        author_wrap_applied=True,
    )
    screened = [
        EvidenceRecord(pmid="1", title="T", screening_status=ScreeningStatus.INCLUDE),
    ]
    snapshot = json.loads(to_search_snapshot(search, records=screened))
    assert snapshot["screening_summary"]["Include"] == 1
    assert snapshot["missing_pmids"] == ["9"]
    assert snapshot["dedupe_removed_pmids"] == ["8"]
    assert snapshot["raw_query"] == "plain name"
    assert snapshot["author_wrap_applied"] is True


def test_filter_records_for_export_scopes():
    records = [
        EvidenceRecord(pmid="1", title="A", screening_status=ScreeningStatus.INCLUDE),
        EvidenceRecord(pmid="2", title="B", screening_status=ScreeningStatus.MAYBE),
        EvidenceRecord(pmid="3", title="C", screening_status=ScreeningStatus.EXCLUDE),
        EvidenceRecord(pmid="4", title="D"),
    ]
    filtered = records[:1]
    assert [r.pmid for r in filter_records_for_export(records, "all")] == ["1", "2", "3", "4"]
    assert [r.pmid for r in filter_records_for_export(records, "include_maybe")] == ["1", "2"]
    assert [r.pmid for r in filter_records_for_export(records, "include")] == ["1"]
    assert [r.pmid for r in filter_records_for_export(records, "filtered", filtered)] == ["1"]


def test_csv_drops_exclusion_reason_after_include():
    records = [
        EvidenceRecord(
            pmid="1",
            title="T",
            screening_status=ScreeningStatus.INCLUDE,
            exclusion_reason=None,
        )
    ]
    csv_text = to_csv(records)
    assert "Animal study" not in csv_text


def test_audit_report_contains_query_and_screening():
    search = SearchResult(
        search_id="abc123",
        research_question="2型糖尿病与二甲双胍",
        query="(diabetes[MeSH]) AND metformin",
        year_from=2020,
        year_to=2024,
        retmax=10,
        total_hits=440,
        records=[
            EvidenceRecord(pmid="1", title="A", screening_status=ScreeningStatus.INCLUDE),
            EvidenceRecord(pmid="2", title="B", screening_status=ScreeningStatus.EXCLUDE),
        ],
        executed_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
        missing_pmids=["99"],
        dedupe_removed_pmids=["88"],
    )
    report = to_audit_report_md(search)
    assert "# Evidence Copilot 检索审计报告" in report
    assert "abc123" in report
    assert "(diabetes[MeSH]) AND metformin" in report
    assert "440" in report
    assert "Include" in report
    assert "99" in report
    assert "88" in report
    assert "2型糖尿病与二甲双胍" in report
