"""烟测：核心链路快速验证（需 NCBI_EMAIL）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config.ncbi_credentials import has_ncbi_email
from src.models.evidence import ScreeningStatus
from src.services.export import to_csv, to_ris
from src.services.screening import count_by_status, update_record
from src.services.search import SearchParams, run_search
from src.services.storage import load_workspace, save_workspace, workspace_from_json, workspace_to_json


@pytest.mark.skipif(not has_ncbi_email(), reason="需要 NCBI 邮箱（设置页、.env 或 workspace.json）")
def test_smoke_pubmed_search():
    """真实 PubMed 检索能返回文献。"""
    result = run_search(
        SearchParams(
            research_question="烟测",
            query="diabetes[Title]",
            year_from=2020,
            year_to=2024,
            retmax=10,
        )
    )
    assert result.total_hits > 0
    assert 1 <= len(result.records) <= 10
    assert result.records[0].pmid
    assert result.records[0].title


@pytest.mark.skipif(not has_ncbi_email(), reason="需要 NCBI 邮箱（设置页、.env 或 workspace.json）")
def test_smoke_screening_export_persist(tmp_path: Path):
    """初筛 → 导出 → 持久化往返。"""
    result = run_search(
        SearchParams(
            research_question="烟测持久化",
            query="hypertension[Title]",
            year_from=2021,
            year_to=2024,
            retmax=10,
        )
    )
    records = [r.model_copy(deep=True) for r in result.records]
    assert len(records) >= 2

    records = update_record(records, records[0].pmid, ScreeningStatus.INCLUDE, notes="smoke")
    counts = count_by_status(records)
    assert counts["Include"] == 1
    result.records = records

    assert "TY  - JOUR" in to_ris(records)
    assert records[0].pmid in to_csv(records)

    path = tmp_path / "workspace.json"
    save_workspace([result], result, "smoke@test.com", path=path)
    loaded = load_workspace(path=path)
    assert loaded is not None
    assert loaded.ncbi_email == "smoke@test.com"
    assert loaded.records[0].screening_status == ScreeningStatus.INCLUDE
    assert loaded.records[0].notes == "smoke"

    text = workspace_to_json([result], result, "smoke@test.com")
    assert "ncbi_api_key" not in json.loads(text)
    restored = workspace_from_json(text)
    assert restored.history[0].search_id == result.search_id
