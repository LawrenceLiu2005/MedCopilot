"""ResearchProject 模型与存储测试。"""

from __future__ import annotations

from pathlib import Path

from src.models.research_project import ProjectState, ResearchProject
from src.services.research_project_storage import load_projects, save_projects, upsert_project


def test_research_project_audit_trail(tmp_path: Path) -> None:
    store = tmp_path / "projects.json"
    project = ResearchProject(research_idea="肝癌术后复发")
    project.append_audit("idea_saved", "保存研究想法", actor="user")
    upsert_project(project, store)

    loaded = load_projects(store)
    assert len(loaded) == 1
    assert loaded[0].state == ProjectState.IDEA
    assert len(loaded[0].audit_trail) == 1
    assert loaded[0].audit_trail[0].summary == "保存研究想法"


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "projects.json"
    first = ResearchProject(title="测试项目", research_idea="测试")
    second = ResearchProject(title="第二个", research_idea="B")
    save_projects([first, second], store)
    loaded = load_projects(store)
    assert {item.title for item in loaded} == {"测试项目", "第二个"}
