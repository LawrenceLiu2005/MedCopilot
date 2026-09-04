"""ResearchProject 领域模型（独立于 Agent 会话状态）。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.evidence import EvidenceRecord
from src.services.search import SearchResult


class ProjectState(str, Enum):
    """科研流程状态机（PRD v2.1 §24）。"""

    IDEA = "IDEA"
    TRIAGED = "TRIAGED"
    QUESTION_DEFINED = "QUESTION_DEFINED"
    EVIDENCE_REVIEWED = "EVIDENCE_REVIEWED"
    GAP_IDENTIFIED = "GAP_IDENTIFIED"
    SEARCHING = "SEARCHING"
    SCREENING = "SCREENING"
    EXTRACTION = "EXTRACTION"
    ANALYSIS = "ANALYSIS"
    COMPLETED = "COMPLETED"


class ResearchDecisionType(str, Enum):
    """需人工确认的关键决策类型。"""

    RESEARCH_QUESTION = "research_question"
    SEARCH_QUERY = "search_query"
    SEARCH_EXECUTION = "search_execution"
    SCREENING = "screening"
    EXTRACTION = "extraction"


class ResearchQuestionDraft(BaseModel):
    """结构化研究问题草稿；未确认前不是 canonical question。"""

    original_text: str
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    uncertainties: list[str] = Field(default_factory=list)
    confirmed: bool = False
    confirmed_at: datetime | None = None


class ProposedSearch(BaseModel):
    """Agent 提议的 PubMed 检索；执行前须审批。"""

    query: str
    research_question: str = ""
    year_from: int | None = None
    year_to: int | None = None
    retmax: int = 50
    rationale: str = ""
    approved: bool = False
    approved_at: datetime | None = None


class AuditEvent(BaseModel):
    """可追溯审计事件。"""

    event_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    event_type: str
    decision_type: ResearchDecisionType | None = None
    summary: str
    payload: dict | None = None
    actor: str = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchProject(BaseModel):
    """持久化科研项目（非 Agent 内存）。"""

    project_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    title: str = ""
    state: ProjectState = ProjectState.IDEA
    research_idea: str = ""
    question: ResearchQuestionDraft | None = None
    proposed_search: ProposedSearch | None = None
    search_runs: list[SearchResult] = Field(default_factory=list)
    active_search_id: str | None = None
    records: list[EvidenceRecord] = Field(default_factory=list)
    audit_trail: list[AuditEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def append_audit(
        self,
        event_type: str,
        summary: str,
        *,
        decision_type: ResearchDecisionType | None = None,
        payload: dict | None = None,
        actor: str = "user",
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            decision_type=decision_type,
            summary=summary,
            payload=payload,
            actor=actor,
        )
        self.audit_trail.append(event)
        self.updated_at = datetime.now(timezone.utc)
        return event
