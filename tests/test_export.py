"""导出功能测试。"""

import json
from datetime import datetime, timezone

from src.models.evidence import EvidenceRecord, ExtractionData, ScreeningStatus
from src.services.export import (
    filter_records_for_export,
    to_audit_report_md,
    to_csv,
    to_methods_draft_md,
    to_ris,
    to_search_snapshot,
)
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
    assert snapshot["suggested_query"] is None
    assert snapshot["ctgov_hits"] == []
    assert snapshot["pico_ai_used"] is False
    assert snapshot["pico_ai_draft"] is None
    assert snapshot["extraction_ai"] == []


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


def test_audit_report_keeps_suggested_and_actual_query():
    search = SearchResult(
        search_id="s1",
        research_question="",
        query="final query",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=1,
        records=[EvidenceRecord(pmid="1", title="A")],
        executed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        suggested_query="suggested query",
    )
    report = to_audit_report_md(search)
    assert "suggested query" in report
    assert "final query" in report
    assert "实际发送的检索式与建议式不同" in report


def test_audit_report_includes_translations():
    search = SearchResult(
        search_id="t1",
        research_question="",
        query="diabetes AND metformin",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=1,
        records=[EvidenceRecord(pmid="1", title="A")],
        executed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        translated_wos='ALL=(diabetes AND metformin)',
        translated_ebsco="TX (diabetes AND metformin)",
    )
    report = to_audit_report_md(search)
    assert "Web of Science" in report
    assert "ALL=(diabetes AND metformin)" in report
    assert "EBSCOHost" in report


def test_methods_draft_fills_known_prisma_s_items():
    search = SearchResult(
        search_id="m1",
        research_question="RQ",
        query="(diabetes[MeSH]) AND metformin",
        year_from=2020,
        year_to=2024,
        retmax=10,
        total_hits=100,
        records=[
            EvidenceRecord(pmid="1", title="A", screening_status=ScreeningStatus.INCLUDE),
            EvidenceRecord(pmid="2", title="B", screening_status=ScreeningStatus.EXCLUDE),
        ],
        executed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        inclusion_criteria="成人 2 型糖尿病",
        translated_ebsco="MH diabetes AND metformin",
    )
    draft = to_methods_draft_md(search)
    assert "# 检索方法草稿（PRISMA-S）" in draft
    assert "需作者补全" in draft
    assert "(diabetes[MeSH]) AND metformin" in draft
    assert "2020" in draft
    assert "100" in draft
    assert "纳入 1 篇" in draft
    assert "成人 2 型糖尿病" in draft
    assert "MH diabetes AND metformin" in draft
    assert "ClinicalTrials.gov" in draft


def test_csv_includes_reviewer2_column():
    records = [
        EvidenceRecord(
            pmid="1",
            title="T",
            screening_status=ScreeningStatus.INCLUDE,
            reviewer2_status=ScreeningStatus.EXCLUDE,
        )
    ]
    csv_text = to_csv(records)
    assert "Reviewer 2 Status" in csv_text
    assert "Exclude" in csv_text


def test_audit_and_snapshot_include_pico_ai_without_secrets():
    search = SearchResult(
        search_id="ai1",
        research_question="肝癌合并糖尿病",
        query="metformin[MeSH Terms]",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=1,
        records=[EvidenceRecord(pmid="1", title="A")],
        executed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        pico_ai_used=True,
        pico_ai_model="deepseek-v4-flash",
        pico_ai_prompt_version="pico_extract_v1",
        pico_ai_source_text="肝癌合并糖尿病的病人",
        pico_ai_draft={"intervention": ["metformin"]},
        pico_ai_accepted={"intervention": "metformin"},
    )
    snapshot = json.loads(to_search_snapshot(search))
    assert snapshot["pico_ai_used"] is True
    assert snapshot["pico_ai_model"] == "deepseek-v4-flash"
    assert "DEEPSEEK_API_KEY" not in json.dumps(snapshot)
    report = to_audit_report_md(search)
    assert "白话拆分" in report
    assert "deepseek-v4-flash" in report
    assert "肝癌合并糖尿病的病人" in report
    assert "pico_extract_v1" in report


def test_audit_and_snapshot_include_extraction_ai_without_secrets():
    search = SearchResult(
        search_id="ex1",
        research_question="RQ",
        query="metformin[MeSH Terms]",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=1,
        records=[
            EvidenceRecord(
                pmid="99",
                title="A",
                screening_status=ScreeningStatus.INCLUDE,
                extraction=ExtractionData(
                    e1=1,
                    n1=10,
                    e2=2,
                    n2=10,
                    ai_used=True,
                    ai_model="deepseek-v4-flash",
                    ai_prompt_version="extraction_suggest_v1",
                    ai_quote="1/10 vs 2/10",
                    ai_draft={"e1": 1, "n1": 10, "e2": 2, "n2": 10},
                    ai_accepted={"e1": 1, "n1": 10, "e2": 2, "n2": 10},
                ),
            )
        ],
        executed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )
    snapshot = json.loads(to_search_snapshot(search))
    assert snapshot["extraction_ai"][0]["pmid"] == "99"
    assert snapshot["extraction_ai"][0]["ai_prompt_version"] == "extraction_suggest_v1"
    dumped = json.dumps(snapshot)
    assert "DEEPSEEK_API_KEY" not in dumped
    report = to_audit_report_md(search)
    assert "提取草稿" in report
    assert "99" in report
    assert "extraction_suggest_v1" in report
    methods = to_methods_draft_md(search)
    assert "提取说明" in methods
