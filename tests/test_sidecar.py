"""Python 侧车 CLI 测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.search import SearchResult
from src.sidecar import __main__ as sidecar_main
from src.sidecar.handlers import (
    handle_export_project,
    handle_get_settings,
    handle_ping,
    handle_propose_search,
    handle_run_pubmed_search,
    handle_save_settings,
    handle_update_screening,
)
from src.services.research_project_storage import get_project


def _stub_pico(mock_extract) -> None:
    mock_extract.return_value = type(
        "Pico",
        (),
        {
            "population": ["demo population"],
            "intervention": [],
            "comparator": [],
            "outcome": ["demo outcome"],
            "has_concepts": lambda self: True,
        },
    )()


def test_handle_ping() -> None:
    result = handle_ping({})
    assert result["ok"] is True
    assert result["service"] == "evidence-copilot-sidecar"


def test_dispatch_unknown_command(capsys) -> None:
    code = sidecar_main.main(["--command", "missing", "--params", "{}"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "未知命令" in payload["error"]


@patch("src.sidecar.handlers.extract_pico")
def test_propose_search_without_pico(mock_extract, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_COPILOT_DATA_DIR", str(tmp_path))
    _stub_pico(mock_extract)

    result = handle_propose_search({"research_idea": "肝癌术后复发"})
    assert result["proposed_query"]
    assert result["requires_approval"] is True
    assert result["project_id"]


@patch("src.sidecar.handlers.run_search")
@patch("src.sidecar.handlers.extract_pico")
def test_run_pubmed_requires_approval(mock_extract, _mock_run, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_COPILOT_DATA_DIR", str(tmp_path))
    _stub_pico(mock_extract)
    proposed = handle_propose_search({"research_idea": "测试问题"})
    with pytest.raises(ValueError, match="尚未获批准"):
        handle_run_pubmed_search(
            {"project_id": proposed["project_id"], "query": "test", "approved": False}
        )


@patch("src.sidecar.handlers.extract_pico")
@patch("src.sidecar.handlers.run_search")
def test_run_pubmed_after_approval(mock_run, mock_extract, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_COPILOT_DATA_DIR", str(tmp_path))
    _stub_pico(mock_extract)
    record = EvidenceRecord(
        pmid="123",
        title="Test paper",
        authors=[],
        journal="Demo",
        publication_year=2024,
        publication_types=[],
        abstract="",
        screening_status=ScreeningStatus.UNSCREENED,
    )
    mock_run.return_value = SearchResult(
        search_id="abc123",
        research_question="测试",
        query="(test)",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=1,
        records=[record],
        executed_at=record.retrieved_at,
    )
    proposed = handle_propose_search({"research_idea": "测试问题"})
    result = handle_run_pubmed_search(
        {
            "project_id": proposed["project_id"],
            "query": "(test)",
            "approved": True,
            "retmax": 10,
        }
    )
    assert result["search_id"] == "abc123"
    assert result["retrieved"] == 1


def test_settings_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_COPILOT_DATA_DIR", str(tmp_path))
    saved = handle_save_settings(
        {
            "ncbi_email": "demo@example.com",
            "ncbi_api_key": "secret-key",
        }
    )
    assert saved["has_ncbi_email"] is True
    assert saved["ncbi_api_key_set"] is True

    loaded = handle_get_settings({})
    assert loaded["ncbi_email"] == "demo@example.com"
    assert loaded["ncbi_api_key_hint"].endswith("ey")


@patch("src.sidecar.handlers.extract_pico")
@patch("src.sidecar.handlers.run_search")
def test_sidecar_e2e_propose_search_screen_export(
    mock_run,
    mock_extract,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("EVIDENCE_COPILOT_DATA_DIR", str(tmp_path))
    _stub_pico(mock_extract)
    record = EvidenceRecord(
        pmid="123",
        title="Test paper",
        authors=["A Author"],
        journal="Demo Journal",
        publication_year=2024,
        publication_types=["Journal Article"],
        abstract="Demo abstract",
        screening_status=ScreeningStatus.UNSCREENED,
    )
    mock_run.return_value = SearchResult(
        search_id="abc123",
        research_question="测试",
        query="(test)",
        year_from=None,
        year_to=None,
        retmax=10,
        total_hits=1,
        records=[record],
        executed_at=record.retrieved_at,
    )

    proposed = handle_propose_search({"research_idea": "测试问题"})
    project_id = proposed["project_id"]
    search_result = handle_run_pubmed_search(
        {
            "project_id": project_id,
            "query": "(test)",
            "approved": True,
        }
    )
    assert search_result["retrieved"] == 1

    screened = handle_update_screening(
        {
            "project_id": project_id,
            "pmid": "123",
            "status": "Include",
        }
    )
    assert screened["screening_status"] == "Include"
    assert screened["stats"]["Include"] == 1

    exported = handle_export_project({"project_id": project_id, "format": "snapshot"})
    assert exported["filename"].endswith(".json")
    assert "abc123" in exported["content"]

    project = get_project(project_id)
    assert project is not None
    event_types = {item.event_type for item in project.audit_trail}
    assert "propose_search" in event_types
    assert "search_executed" in event_types
    assert "screening_updated" in event_types
    assert "export" in event_types
