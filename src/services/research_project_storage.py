"""ResearchProject 本地持久化（桌面版默认路径）。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pydantic import TypeAdapter

from src.models.research_project import ResearchProject
from src.services.storage import _search_result_from_dict, _search_result_to_dict

PROJECT_STORE_VERSION = 1
_PROJECT_ADAPTER = TypeAdapter(ResearchProject)


def default_data_dir() -> Path:
    """桌面版数据目录；开发时回退到 .data/desktop。"""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "EvidenceCopilot"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "EvidenceCopilot"
    else:
        base = Path.home() / ".local" / "share" / "EvidenceCopilot"
    env = os.environ.get("EVIDENCE_COPILOT_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if not base.exists() and Path(".data/desktop").exists():
        return Path(".data/desktop")
    return base


def project_store_path(data_dir: Path | None = None) -> Path:
    root = data_dir or default_data_dir()
    return root / "research_projects.json"


def _project_to_dict(project: ResearchProject) -> dict:
    data = project.model_dump(mode="json")
    data["search_runs"] = [_search_result_to_dict(item) for item in project.search_runs]
    return data


def _project_from_dict(data: dict) -> ResearchProject:
    runs = [_search_result_from_dict(item) for item in data.get("search_runs", [])]
    payload = {**data, "search_runs": runs}
    return _PROJECT_ADAPTER.validate_python(payload)


def load_projects(path: Path | None = None) -> list[ResearchProject]:
    target = path or project_store_path()
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if payload.get("version") != PROJECT_STORE_VERSION:
        return []
    return [_project_from_dict(item) for item in payload.get("projects", [])]


def save_projects(projects: list[ResearchProject], path: Path | None = None) -> Path:
    target = path or project_store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": PROJECT_STORE_VERSION,
        "projects": [_project_to_dict(item) for item in projects],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def get_project(project_id: str, path: Path | None = None) -> ResearchProject | None:
    for project in load_projects(path):
        if project.project_id == project_id:
            return project
    return None


def upsert_project(project: ResearchProject, path: Path | None = None) -> Path:
    projects = load_projects(path)
    replaced = False
    for index, existing in enumerate(projects):
        if existing.project_id == project.project_id:
            projects[index] = project
            replaced = True
            break
    if not replaced:
        projects.append(project)
    return save_projects(projects, path)
