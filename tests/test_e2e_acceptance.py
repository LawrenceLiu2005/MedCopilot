"""PRD §13 端到端验收（需 NCBI_EMAIL）。"""

from __future__ import annotations

import json

import pytest

from src.config.ncbi_credentials import has_ncbi_email
from src.models.evidence import ScreeningStatus
from src.services.export import to_csv, to_ris, to_search_snapshot
from src.services.screening import count_by_status, dedupe_records, flag_potential_duplicates, update_record
from src.services.search import SearchParams, run_search

MEDICAL_QUERY = (
    "(diabetes mellitus, type 2[MeSH]) AND metformin[Title/Abstract] "
    "AND randomized controlled trial[pt]"
)


@pytest.mark.skipif(not has_ncbi_email(), reason="需要 NCBI 邮箱（设置页、.env 或 workspace.json）")
def test_prd_e2e_real_medical_topic():
    """真实医学主题：搜索 → 初筛 → 导出 → 快照。"""
    result = run_search(
        SearchParams(
            research_question="2型糖尿病成人患者使用二甲双胍的随机对照试验疗效",
            query=MEDICAL_QUERY,
            year_from=2020,
            year_to=2024,
            retmax=10,
        )
    )
    result.records = flag_potential_duplicates(dedupe_records(result.records).records)

    assert result.total_hits > 0
    assert 1 <= len(result.records) <= 10
    assert result.records[0].pmid
    assert result.records[0].title

    records = [record.model_copy(deep=True) for record in result.records]
    records = update_record(records, records[0].pmid, ScreeningStatus.INCLUDE, notes="E2E include")
    records = update_record(
        records,
        records[1].pmid,
        ScreeningStatus.EXCLUDE,
        exclusion_reason="Wrong study design",
        notes="E2E exclude",
    )

    counts = count_by_status(records)
    assert counts["Total"] == len(records)
    assert counts["Include"] == 1
    assert counts["Exclude"] == 1

    assert "TY  - JOUR" in to_ris(records)
    csv_text = to_csv(records)
    assert "PMID" in csv_text and "Screening Status" in csv_text

    snapshot = json.loads(to_search_snapshot(result))
    assert snapshot["exact_query"] == MEDICAL_QUERY
    assert snapshot["total_hits"] == result.total_hits
    assert len(snapshot["retrieved_pmids"]) == len(result.records)
