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
        "pico_population": result.pico_population,
        "pico_intervention": result.pico_intervention,
        "pico_comparator": result.pico_comparator,
        "pico_outcome": result.pico_outcome,
        "inclusion_criteria": result.inclusion_criteria,
        "exclusion_criteria": result.exclusion_criteria,
        "source_type": result.source_type,
        "parent_search_id": result.parent_search_id,
        "translated_wos": result.translated_wos,
        "translated_ebsco": result.translated_ebsco,
        "suggested_query": result.suggested_query,
        "query_suggestion_blocks": result.query_suggestion_blocks,
        "study_types": result.study_types,
        "ctgov_query": result.ctgov_query,
        "ctgov_hits": result.ctgov_hits,
        "pico_ai_used": result.pico_ai_used,
        "pico_ai_model": result.pico_ai_model,
        "pico_ai_prompt_version": result.pico_ai_prompt_version,
        "pico_ai_source_text": result.pico_ai_source_text,
        "pico_ai_draft": result.pico_ai_draft,
        "pico_ai_accepted": result.pico_ai_accepted,
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
        pico_population=data.get("pico_population") or "",
        pico_intervention=data.get("pico_intervention") or "",
        pico_comparator=data.get("pico_comparator") or "",
        pico_outcome=data.get("pico_outcome") or "",
        inclusion_criteria=data.get("inclusion_criteria") or "",
        exclusion_criteria=data.get("exclusion_criteria") or "",
        source_type=data.get("source_type") or "pubmed_search",
        parent_search_id=data.get("parent_search_id"),
        translated_wos=data.get("translated_wos"),
        translated_ebsco=data.get("translated_ebsco"),
        suggested_query=data.get("suggested_query"),
        query_suggestion_blocks=data.get("query_suggestion_blocks"),
        study_types=data.get("study_types"),
        ctgov_query=data.get("ctgov_query"),
        ctgov_hits=data.get("ctgov_hits"),
        pico_ai_used=bool(data.get("pico_ai_used", False)),
        pico_ai_model=data.get("pico_ai_model"),
        pico_ai_prompt_version=data.get("pico_ai_prompt_version"),
        pico_ai_source_text=data.get("pico_ai_source_text"),
        pico_ai_draft=data.get("pico_ai_draft"),
        pico_ai_accepted=data.get("pico_ai_accepted"),
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
