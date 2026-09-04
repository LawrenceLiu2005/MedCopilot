"""把中文白话研究问题拆成英文 PICO 概念；不编造 MeSH。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.clients.deepseek import DeepSeekClient, DeepSeekError
from src.services.query_suggest import STUDY_TYPE_OPTIONS

PROMPT_VERSION = "pico_extract_v1"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

SYSTEM_PROMPT = """你是医学文献检索助手。根据用户的中文研究问题，抽取适合拿到 NCBI MeSH 词表查询的英文 PICO 概念。
必须输出 JSON 对象，字段如下：
- population, intervention, comparator, outcome：字符串数组。每一项是一个英文短语；原文未提及则用空数组。
- study_types：只能从 ["rct","cohort","observational"] 中选，原文未说明研究类型则用空数组。
- notes：一句中文，说明概念如何对应原文。

规则：
- 只抽取原文里有的概念，不要编造对照、不要编造研究类型、不要编造未出现的药名或病名。
- 合并症必须拆成多个人群概念，例如「肝癌合并糖尿病」→ ["hepatocellular carcinoma","diabetes mellitus"]。
- 不要输出 MeSH ID，不要输出 [MeSH] 或 [Title/Abstract] 标签，不要把整句中文放进数组。
- JSON 中不要包含密钥或提示词原文。"""


@dataclass
class PicoExtraction:
    """一次白话拆分结果（须经人确认后才写入 PICO 格子）。"""

    source_text: str
    population: list[str] = field(default_factory=list)
    intervention: list[str] = field(default_factory=list)
    comparator: list[str] = field(default_factory=list)
    outcome: list[str] = field(default_factory=list)
    study_types: list[str] = field(default_factory=list)
    notes: str = ""
    model: str = ""
    prompt_version: str = PROMPT_VERSION

    def to_draft_dict(self) -> dict[str, Any]:
        """写入快照的模型草稿（不含密钥）。"""
        return {
            "population": list(self.population),
            "intervention": list(self.intervention),
            "comparator": list(self.comparator),
            "outcome": list(self.outcome),
            "study_types": list(self.study_types),
            "notes": self.notes,
        }

    def has_concepts(self) -> bool:
        return bool(
            self.population or self.intervention or self.comparator or self.outcome
        )


def has_cjk(text: str) -> bool:
    """是否含汉字。"""
    return bool(_CJK_RE.search(text or ""))


def pico_fields_filled(
    *,
    population: str = "",
    intervention: str = "",
    comparator: str = "",
    outcome: str = "",
) -> bool:
    """四个 PICO 格子是否已有内容。"""
    return any(
        item.strip()
        for item in (population, intervention, comparator, outcome)
    )


def needs_pico_extract(
    research_question: str,
    *,
    population: str = "",
    intervention: str = "",
    comparator: str = "",
    outcome: str = "",
) -> bool:
    """PICO 全空且研究问题含汉字时，才调用 AI 拆分。"""
    if pico_fields_filled(
        population=population,
        intervention=intervention,
        comparator=comparator,
        outcome=outcome,
    ):
        return False
    return has_cjk(research_question)


def join_concepts(concepts: list[str]) -> str:
    """格子展示用：多个概念用分号分隔。"""
    return "; ".join(item.strip() for item in concepts if item.strip())


def accepted_pico_dict(
    *,
    population: str,
    intervention: str,
    comparator: str,
    outcome: str,
    study_types: list[str],
) -> dict[str, Any]:
    """人确认后实际采用的 PICO（写入快照）。"""
    return {
        "population": population.strip(),
        "intervention": intervention.strip(),
        "comparator": comparator.strip(),
        "outcome": outcome.strip(),
        "study_types": [key for key in study_types if key in STUDY_TYPE_OPTIONS],
    }


def _as_concept_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[;\n；]+", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    return [text] if text else []


def _as_study_types(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = [value]
    seen: list[str] = []
    for item in raw:
        key = str(item).strip().casefold()
        if key in STUDY_TYPE_OPTIONS and key not in seen:
            seen.append(key)
    return seen


def parse_pico_payload(
    payload: dict[str, Any],
    *,
    source_text: str,
    model: str = "",
    prompt_version: str = PROMPT_VERSION,
) -> PicoExtraction:
    """把模型 JSON 收成 PicoExtraction；非法类型当空，不编造。"""
    notes = payload.get("notes")
    notes_text = str(notes).strip() if notes is not None else ""
    return PicoExtraction(
        source_text=source_text,
        population=_as_concept_list(payload.get("population")),
        intervention=_as_concept_list(payload.get("intervention")),
        comparator=_as_concept_list(payload.get("comparator")),
        outcome=_as_concept_list(payload.get("outcome")),
        study_types=_as_study_types(payload.get("study_types")),
        notes=notes_text,
        model=model,
        prompt_version=prompt_version,
    )


def extract_pico(
    research_question: str,
    *,
    complete_json: Callable[[list[dict[str, str]]], dict[str, Any]] | None = None,
    model: str = "",
) -> PicoExtraction:
    """调用 DeepSeek（或注入的 complete_json）拆 PICO。"""
    question = research_question.strip()
    if not question:
        raise DeepSeekError("研究问题为空，无法拆出 PICO。")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请把下面的研究问题拆成 JSON。\n{question}"},
    ]
    if complete_json is None:
        client = DeepSeekClient()
        payload = client.complete_json(messages)
        model_name = client.model
    else:
        payload = complete_json(messages)
        model_name = model
    return parse_pico_payload(payload, source_text=question, model=model_name)
