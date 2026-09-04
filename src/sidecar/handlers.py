"""侧车命令处理器。"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.evidence import ScreeningStatus
from src.models.research_project import (
    ProjectState,
    ProposedSearch,
    ResearchDecisionType,
    ResearchProject,
    ResearchQuestionDraft,
)
from src.config.desktop_settings import get_settings_payload, save_settings_payload
from src.services.pico_extract import extract_pico, join_concepts
from src.services.research_project_storage import get_project, upsert_project
from src.services.screening import count_by_status, update_record
from src.services.search import SearchParams, run_search


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def handle_ping(_params: dict) -> dict:
    return {"ok": True, "service": "evidence-copilot-sidecar", "time": _now_iso()}


def handle_propose_search(params: dict) -> dict:
    """从白话研究想法生成检索提议（不执行 PubMed）。"""
    idea = str(params.get("research_idea") or params.get("research_question") or "").strip()
    if not idea:
        raise ValueError("缺少 research_idea。")

    project_id = params.get("project_id")
    project = get_project(project_id) if project_id else None
    if project is None:
        project = ResearchProject(research_idea=idea, title=idea[:80])
    else:
        project.research_idea = idea

    pico_result = None
    pico_error = None
    try:
        pico_result = extract_pico(idea)
    except Exception as exc:  # noqa: BLE001 — 侧车需返回可读错误，不伪造 PICO
        pico_error = str(exc)

    blocks = []
    query_parts: list[str] = []
    if pico_result and pico_result.has_concepts():
        for label, concepts in (
            ("Population", pico_result.population),
            ("Intervention", pico_result.intervention),
            ("Comparator", pico_result.comparator),
            ("Outcome", pico_result.outcome),
        ):
            text = join_concepts(concepts)
            if text:
                blocks.append({"label": label, "text": text})
                query_parts.append(f"({text})")

    proposed_query = " AND ".join(query_parts) if query_parts else idea
    uncertainties: list[str] = []
    if not pico_result or not pico_result.population:
        uncertainties.append("人群定义尚未明确")
    if not pico_result or not pico_result.outcome:
        uncertainties.append("结局定义尚未明确")
    if pico_error:
        uncertainties.append(f"PICO 草稿生成失败：{pico_error}")

    project.question = ResearchQuestionDraft(
        original_text=idea,
        population=join_concepts(pico_result.population) if pico_result else None,
        intervention=join_concepts(pico_result.intervention) if pico_result else None,
        comparator=join_concepts(pico_result.comparator) if pico_result else None,
        outcome=join_concepts(pico_result.outcome) if pico_result else None,
        uncertainties=uncertainties,
        confirmed=False,
    )
    project.proposed_search = ProposedSearch(
        query=proposed_query,
        research_question=idea,
        year_from=params.get("year_from"),
        year_to=params.get("year_to"),
        retmax=int(params.get("retmax") or 50),
        rationale="基于 PICO 概念块组合的可编辑检索式提议；执行前须人工确认。",
        approved=False,
    )
    project.state = ProjectState.TRIAGED
    project.append_audit(
        "propose_search",
        "Agent 提议 PubMed 检索式（未执行）",
        decision_type=ResearchDecisionType.SEARCH_QUERY,
        payload={"query": proposed_query},
        actor="agent",
    )
    upsert_project(project)

    return {
        "project_id": project.project_id,
        "research_idea": idea,
        "pico_blocks": blocks,
        "proposed_query": proposed_query,
        "uncertainties": uncertainties,
        "rationale": project.proposed_search.rationale,
        "requires_approval": True,
    }


def handle_run_pubmed_search(params: dict) -> dict:
    """仅在 approved=true 时执行 PubMed 检索。"""
    project_id = str(params.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("缺少 project_id。")
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"找不到项目：{project_id}")

    approved = bool(params.get("approved"))
    if not approved:
        raise ValueError("PubMed 检索尚未获批准；请先确认 proposed_query。")

    query = str(params.get("query") or "").strip()
    if not query and project.proposed_search:
        query = project.proposed_search.query
    if not query:
        raise ValueError("缺少 PubMed query。")

    retmax = int(params.get("retmax") or (project.proposed_search.retmax if project.proposed_search else 50))
    year_from = params.get("year_from")
    year_to = params.get("year_to")
    if project.proposed_search:
        year_from = year_from if year_from is not None else project.proposed_search.year_from
        year_to = year_to if year_to is not None else project.proposed_search.year_to

    search_params = SearchParams(
        research_question=project.research_idea,
        query=query,
        year_from=year_from,
        year_to=year_to,
        retmax=retmax,
        sort=params.get("sort"),
        pico_population=project.question.population if project.question else "",
        pico_intervention=project.question.intervention if project.question else "",
        pico_comparator=project.question.comparator if project.question else "",
        pico_outcome=project.question.outcome if project.question else "",
    )
    result = run_search(search_params)

    if project.proposed_search:
        project.proposed_search.query = query
        project.proposed_search.approved = True
        project.proposed_search.approved_at = datetime.now(timezone.utc)

    project.search_runs.append(result)
    project.active_search_id = result.search_id
    project.records = [item.model_copy(deep=True) for item in result.records]
    project.state = ProjectState.SEARCHING
    project.append_audit(
        "search_executed",
        f"已执行 PubMed 检索：{query}",
        decision_type=ResearchDecisionType.SEARCH_EXECUTION,
        payload={"search_id": result.search_id, "total_hits": result.total_hits},
        actor="user",
    )
    upsert_project(project)

    return {
        "project_id": project.project_id,
        "search_id": result.search_id,
        "query": result.query,
        "total_hits": result.total_hits,
        "retrieved": len(result.records),
        "records": [
            {
                "pmid": record.pmid,
                "title": record.title,
                "journal": record.journal,
                "publication_year": record.publication_year,
                "screening_status": record.screening_status.value,
                "exclusion_reason": record.exclusion_reason,
                "notes": record.notes,
            }
            for record in result.records
        ],
        "stats": count_by_status(project.records),
    }


def handle_get_project(params: dict) -> dict:
    project_id = str(params.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("缺少 project_id。")
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"找不到项目：{project_id}")
    return project.model_dump(mode="json")


def handle_get_settings(_params: dict) -> dict:
    return get_settings_payload()


def handle_save_settings(params: dict) -> dict:
    return save_settings_payload(params)


def handle_update_screening(params: dict) -> dict:
    project_id = str(params.get("project_id") or "").strip()
    pmid = str(params.get("pmid") or "").strip()
    if not project_id or not pmid:
        raise ValueError("缺少 project_id 或 pmid。")
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"找不到项目：{project_id}")

    status_raw = str(params.get("status") or "").strip()
    try:
        status = ScreeningStatus(status_raw)
    except ValueError as exc:
        raise ValueError(f"无效的初筛状态：{status_raw}") from exc

    exclusion_reason = params.get("exclusion_reason")
    notes = params.get("notes")
    project.records = update_record(
        project.records,
        pmid,
        status,
        str(exclusion_reason) if exclusion_reason else None,
        str(notes) if notes is not None else None,
    )
    project.state = ProjectState.SCREENING
    project.append_audit(
        "screening_updated",
        f"PMID {pmid} → {status.value}",
        decision_type=ResearchDecisionType.SCREENING,
        payload={"pmid": pmid, "status": status.value},
        actor="user",
    )
    upsert_project(project)
    stats = count_by_status(project.records)
    record = next((item for item in project.records if item.pmid == pmid), None)
    return {
        "project_id": project.project_id,
        "pmid": pmid,
        "screening_status": status.value,
        "stats": stats,
        "record": {
            "pmid": record.pmid,
            "title": record.title,
            "journal": record.journal,
            "publication_year": record.publication_year,
            "screening_status": record.screening_status.value,
            "exclusion_reason": record.exclusion_reason,
            "notes": record.notes,
        }
        if record
        else None,
    }


def _active_search(project: ResearchProject):
    if not project.active_search_id:
        return None
    for run in project.search_runs:
        if run.search_id == project.active_search_id:
            return run
    return None


def handle_export_project(params: dict) -> dict:
    from src.services.export import to_csv, to_ris, to_search_snapshot

    project_id = str(params.get("project_id") or "").strip()
    export_format = str(params.get("format") or "csv").strip().lower()
    if not project_id:
        raise ValueError("缺少 project_id。")
    project = get_project(project_id)
    if project is None:
        raise ValueError(f"找不到项目：{project_id}")
    search = _active_search(project)
    if search is None or not project.records:
        raise ValueError("尚无检索结果可导出。")

    if export_format == "ris":
        content = to_ris(project.records)
        filename = f"evidence_copilot_{project.project_id}.ris"
    elif export_format == "csv":
        content = to_csv(project.records)
        filename = f"evidence_copilot_{project.project_id}.csv"
    elif export_format == "snapshot":
        content = to_search_snapshot(search, project.records)
        filename = f"search_snapshot_{search.search_id}.json"
    else:
        raise ValueError(f"不支持的导出格式：{export_format}")

    project.append_audit(
        "export",
        f"导出 {export_format.upper()}：{filename}",
        payload={"format": export_format, "filename": filename},
        actor="user",
    )
    upsert_project(project)
    return {"filename": filename, "content": content, "format": export_format}


HANDLERS = {
    "ping": handle_ping,
    "propose_search": handle_propose_search,
    "run_pubmed_search": handle_run_pubmed_search,
    "get_project": handle_get_project,
    "get_settings": handle_get_settings,
    "save_settings": handle_save_settings,
    "update_screening": handle_update_screening,
    "export_project": handle_export_project,
}
