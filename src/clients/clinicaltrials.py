"""ClinicalTrials.gov API v2 薄客户端（登记库对照，不写入文献记录）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx

CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"
TIMEOUT = 30.0
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


class ClinicalTrialsError(Exception):
    """ClinicalTrials.gov 请求失败。"""


@dataclass(frozen=True)
class ClinicalTrialHit:
    """单条试验登记记录。"""

    nct_id: str
    title: str
    status: str | None
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def hit_from_dict(data: dict) -> ClinicalTrialHit:
    """从已保存字典还原。"""
    nct_id = str(data.get("nct_id") or "")
    return ClinicalTrialHit(
        nct_id=nct_id,
        title=str(data.get("title") or ""),
        status=data.get("status"),
        url=str(data.get("url") or f"https://clinicaltrials.gov/study/{nct_id}"),
    )


def build_ctgov_query(
    *,
    population: str = "",
    intervention: str = "",
    comparator: str = "",
    outcome: str = "",
    research_question: str = "",
) -> str:
    """用 PICO 关键词拼登记库检索式；PICO 全空则用研究问题。"""
    parts = [
        item.strip()
        for item in (population, intervention, comparator, outcome)
        if item and item.strip()
    ]
    if parts:
        return " AND ".join(f"({item})" if " " in item else item for item in parts)
    return research_question.strip()


class ClinicalTrialsClient:
    """ClinicalTrials.gov 检索客户端。"""

    def __init__(self, *, timeout: float = TIMEOUT) -> None:
        self.timeout = timeout

    def search(
        self,
        query: str,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[int | None, list[ClinicalTrialHit]]:
        """按自然语言/关键词检索登记试验，返回 (总命中或 None, 本页列表)。"""
        cleaned = query.strip()
        if not cleaned:
            return 0, []
        size = min(max(page_size, 1), MAX_PAGE_SIZE)
        params = {
            "query.term": cleaned,
            "pageSize": size,
            "format": "json",
        }
        try:
            response = httpx.get(
                CTGOV_BASE,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "EvidenceCopilot/1.0 (systematic-review workbench)"},
            )
        except httpx.HTTPError as exc:
            raise ClinicalTrialsError(f"ClinicalTrials.gov 网络请求失败: {exc}") from exc
        if response.status_code >= 500:
            raise ClinicalTrialsError(f"ClinicalTrials.gov 服务器错误: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ClinicalTrialsError(f"ClinicalTrials.gov 请求被拒绝: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ClinicalTrialsError("ClinicalTrials.gov 返回格式异常。") from exc
        if not isinstance(payload, dict):
            raise ClinicalTrialsError("ClinicalTrials.gov 返回格式异常。")
        total = payload.get("totalCount")
        total_int = int(total) if isinstance(total, int) else None
        hits = [_parse_study(item) for item in payload.get("studies") or []]
        return total_int, [hit for hit in hits if hit is not None]


def _parse_study(study: object) -> ClinicalTrialHit | None:
    if not isinstance(study, dict):
        return None
    protocol = study.get("protocolSection") or {}
    if not isinstance(protocol, dict):
        return None
    ident = protocol.get("identificationModule") or {}
    status_mod = protocol.get("statusModule") or {}
    nct_id = str(ident.get("nctId") or "").strip()
    if not nct_id:
        return None
    title = str(ident.get("briefTitle") or ident.get("officialTitle") or "").strip()
    status = status_mod.get("overallStatus")
    status_text = str(status).strip() if status else None
    return ClinicalTrialHit(
        nct_id=nct_id,
        title=title or "（无标题）",
        status=status_text,
        url=f"https://clinicaltrials.gov/study/{nct_id}",
    )
