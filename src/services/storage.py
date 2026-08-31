"""工作区本地持久化（JSON 文件）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.models.evidence import EvidenceRecord
from src.services.search import SearchResult

WORKSPACE_PATH = Path(".data/workspace.json")
WORKSPACE_VERSION = 1


@dataclass
class WorkspaceData:
    """从磁盘或导入文件还原的工作区。"""

    history: list[SearchResult]
    active_search: SearchResult | None
    records: list[EvidenceRecord]
    ncbi_email: str | None


def _search_result_to_dict(result: SearchResult) -> dict:
    return {
        "search_id": result.search_id,
        "research_question": result.research_question,
        "query": result.query,
        "year_from": result.year_from,
        "year_to": result.year_to,
        "retmax": result.retmax,
        "sort": result.sort,
        "total_hits": result.total_hits,
        "records": [r.model_dump(mode="json") for r in result.records],
        "executed_at": result.executed_at.isoformat(),
        "missing_pmids": result.missing_pmids,
        "dedupe_removed_pmids": result.dedupe_removed_pmids,
        "raw_query": result.raw_query,
        "author_wrap_applied": result.author_wrap_applied,
    }


def _search_result_from_dict(data: dict) -> SearchResult:
    records = [EvidenceRecord.model_validate(r) for r in data["records"]]
    executed_at = datetime.fromisoformat(data["executed_at"])
    if executed_at.tzinfo is None:
        executed_at = executed_at.replace(tzinfo=timezone.utc)
    return SearchResult(
        search_id=data["search_id"],
        research_question=data["research_question"],
        query=data["query"],
        year_from=data["year_from"],
        year_to=data["year_to"],
        retmax=data["retmax"],
        total_hits=data["total_hits"],
        records=records,
        executed_at=executed_at,
        sort=data.get("sort"),
        missing_pmids=data.get("missing_pmids"),
        dedupe_removed_pmids=data.get("dedupe_removed_pmids"),
        raw_query=data.get("raw_query"),
        author_wrap_applied=bool(data.get("author_wrap_applied", False)),
    )


def _build_payload(
    history: list[SearchResult],
    active_search: SearchResult | None,
    ncbi_email: str | None,
) -> dict:
    return {
        "version": WORKSPACE_VERSION,
        "active_search_id": active_search.search_id if active_search else None,
        "ncbi_email": ncbi_email,
        "history": [_search_result_to_dict(item) for item in history],
    }


def _parse_payload(payload: dict) -> WorkspaceData:
    if payload.get("version") != WORKSPACE_VERSION:
        raise ValueError(f"不支持的工作区版本：{payload.get('version')}")

    history = [_search_result_from_dict(item) for item in payload.get("history", [])]
    active_id = payload.get("active_search_id")
    active_search = next((item for item in history if item.search_id == active_id), None)
    records = [r.model_copy(deep=True) for r in active_search.records] if active_search else []
    email = payload.get("ncbi_email")
    ncbi_email = str(email).strip() if email else None
    return WorkspaceData(
        history=history,
        active_search=active_search,
        records=records,
        ncbi_email=ncbi_email,
    )


def workspace_to_json(
    history: list[SearchResult],
    active_search: SearchResult | None,
    ncbi_email: str | None,
) -> str:
    """导出工作区 JSON 文本。"""
    payload = _build_payload(history, active_search, ncbi_email)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def workspace_from_json(text: str) -> WorkspaceData:
    """从 JSON 文本解析工作区。"""
    payload = json.loads(text)
    return _parse_payload(payload)


def load_workspace(path: Path | None = None) -> WorkspaceData | None:
    """从本地文件载入工作区；文件不存在时返回 None。"""
    target = path or WORKSPACE_PATH
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return _parse_payload(payload)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return None


def quarantine_corrupt_workspace(path: Path | None = None) -> Path | None:
    """把损坏的工作区改名为 .bak，避免被空文件覆盖。"""
    target = path or WORKSPACE_PATH
    if not target.is_file():
        return None
    bak = target.with_name(target.name + ".bak")
    if bak.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        bak = target.with_name(f"{target.name}.bak.{stamp}")
    target.rename(bak)
    return bak


def save_workspace(
    history: list[SearchResult],
    active_search: SearchResult | None,
    ncbi_email: str | None,
    path: Path | None = None,
) -> None:
    """写入本地工作区文件。"""
    target = path or WORKSPACE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_payload(history, active_search, ncbi_email)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
