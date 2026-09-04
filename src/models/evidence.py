"""文献数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ScreeningStatus(str, Enum):
    """初筛状态。"""

    UNSCREENED = "Unscreened"
    INCLUDE = "Include"
    MAYBE = "Maybe"
    EXCLUDE = "Exclude"


EXCLUSION_PRESETS: list[str] = [
    "Wrong population",
    "Wrong intervention",
    "Wrong comparator",
    "Wrong outcome",
    "Wrong study design",
    "Wrong publication type",
    "Animal study",
    "Not relevant",
    "Other",
]

class ScreeningHistoryEntry(BaseModel):
    """单条初筛决策变更记录。"""

    status: ScreeningStatus
    exclusion_reason: str | None = None
    notes: str | None = None
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractionData(BaseModel):
    """人工提取的 meta 分析数据；与 PubMed 字段分离，缺失保持 None。"""

    datatype: str | None = None
    e1: int | None = None
    n1: int | None = None
    e2: int | None = None
    n2: int | None = None
    m1: float | None = None
    sd1: float | None = None
    m2: float | None = None
    sd2: float | None = None
    study_label: str | None = None
    subgroup: str | None = None
    ai_used: bool = False
    ai_model: str | None = None
    ai_prompt_version: str | None = None
    ai_quote: str | None = None
    ai_draft: dict | None = None
    ai_accepted: dict | None = None


EXCLUSION_PRESET_ZH: dict[str, str] = {
    "Wrong population": "人群不符",
    "Wrong intervention": "干预不符",
    "Wrong comparator": "对照不符",
    "Wrong outcome": "结局不符",
    "Wrong study design": "研究设计不符",
    "Wrong publication type": "文献类型不符",
    "Animal study": "动物研究",
    "Not relevant": "不相关",
    "Other": "其他",
}


class EvidenceRecord(BaseModel):
    """单篇文献记录。"""

    pmid: str
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    publication_date: str | None = None
    publication_year: int | None = None
    publication_types: list[str] = Field(default_factory=list)
    abstract: str | None = None
    screening_status: ScreeningStatus = ScreeningStatus.UNSCREENED
    reviewer2_status: ScreeningStatus | None = None
    exclusion_reason: str | None = None
    notes: str | None = None
    potential_duplicate: bool = False
    screening_history: list[ScreeningHistoryEntry] = Field(default_factory=list)
    extraction: ExtractionData | None = None
    source: str = "pubmed"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_pubmed_dict(cls, data: dict) -> EvidenceRecord:
        """将 PubMed 解析结果转为 EvidenceRecord；缺失字段保持 None，不猜测。"""
        return cls(
            pmid=str(data["pmid"]),
            doi=data.get("doi"),
            title=data.get("title") or "",
            authors=data.get("authors") or [],
            journal=data.get("journal"),
            publication_date=data.get("publication_date"),
            publication_year=data.get("publication_year"),
            publication_types=data.get("publication_types") or [],
            abstract=data.get("abstract"),
            source="pubmed",
            retrieved_at=datetime.now(timezone.utc),
        )
