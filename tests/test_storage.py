"""工作区持久化测试。"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.search import SearchResult
from src.services.storage import (
    WORKSPACE_VERSION,
    load_workspace,
    quarantine_corrupt_workspace,
    save_workspace,
    workspace_from_json,
    workspace_to_json,
)


def _sample_search() -> SearchResult:
    return SearchResult(
        search_id="abc12345",
        research_question="Test RQ",
        query='"diabetes"[Title]',
        year_from=2020,
        year_to=2024,
        retmax=10,
        total_hits=42,
        records=[
            EvidenceRecord(
                pmid="111",
                title="Paper A",
                screening_status=ScreeningStatus.INCLUDE,
                notes="keep",
            ),
            EvidenceRecord(
                pmid="222",
                title="Paper B",
                screening_status=ScreeningStatus.EXCLUDE,
                exclusion_reason="Not relevant",
            ),
        ],
        executed_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
    )


def test_save_and_load_roundtrip(tmp_path: Path):
    search = _sample_search()
    path = tmp_path / "workspace.json"
    save_workspace([search], search, "user@example.com", path=path)

    loaded = load_workspace(path=path)
    assert loaded is not None
    assert loaded.ncbi_email == "user@example.com"
    assert len(loaded.history) == 1
    assert loaded.active_search is not None
    assert loaded.active_search.search_id == "abc12345"
    assert len(loaded.records) == 2
    assert loaded.records[0].screening_status == ScreeningStatus.INCLUDE
    assert loaded.records[1].exclusion_reason == "Not relevant"


def test_json_import_export_roundtrip():
    search = _sample_search()
    text = workspace_to_json([search], search, "user@example.com")
    loaded = workspace_from_json(text)

    assert loaded.ncbi_email == "user@example.com"
    assert loaded.history[0].query == '"diabetes"[Title]'
    assert loaded.records[0].pmid == "111"


def test_workspace_json_excludes_api_key():
    search = _sample_search()
    payload = json.loads(workspace_to_json([search], search, "user@example.com"))
    assert payload["version"] == WORKSPACE_VERSION
    assert "ncbi_email" in payload
    assert "ncbi_api_key" not in payload


def test_load_missing_file_returns_none(tmp_path: Path):
    assert load_workspace(path=tmp_path / "missing.json") is None


def test_workspace_from_json_rejects_bad_version():
    with pytest.raises(ValueError, match="不支持的工作区版本"):
        workspace_from_json('{"version": 999, "history": []}')


def test_load_corrupt_file_returns_none(tmp_path: Path):
    path = tmp_path / "workspace.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_workspace(path=path) is None
    assert path.is_file()


def test_quarantine_corrupt_workspace_renames_file(tmp_path: Path):
    path = tmp_path / "workspace.json"
    path.write_text("{not json", encoding="utf-8")
    bak = quarantine_corrupt_workspace(path)
    assert bak is not None
    assert not path.exists()
    assert bak.read_text(encoding="utf-8") == "{not json"
    save_workspace([], None, None, path=path)
    assert bak.read_text(encoding="utf-8") == "{not json"
    assert path.is_file()
