"""根据 PICO 与 NCBI MeSH 词表拼检索式建议；不自动搜索、不静默改式。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from src.clients.pubmed import MeshLookupResult, PubMedError

_LATIN_RE = re.compile(r"[A-Za-z]")
_QUOTE_NEEDED_RE = re.compile(r'[\s\[\]\(\)"\']')

STUDY_TYPE_OPTIONS: dict[str, tuple[str, str]] = {
    "rct": ("RCT（随机对照试验）", '"Randomized Controlled Trial"[Publication Type]'),
    "cohort": ("队列研究", '"Cohort Studies"[MeSH Terms]'),
    "observational": ("观察性研究", '"Observational Study"[Publication Type]'),
}

PICO_ROLES: tuple[tuple[str, str], ...] = (
    ("population", "P（人群）"),
    ("intervention", "I（干预）"),
    ("comparator", "C（对照）"),
    ("outcome", "O（结局）"),
)


@dataclass
class QueryBlock:
    """检索式中的一块（一个 PICO 概念或研究类型）。"""

    role: str
    label: str
    original: str
    mesh_matched: bool
    clause: str
    mesh_descriptor: str | None = None
    terms_used: list[str] = field(default_factory=list)
    unmatched_concepts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QuerySuggestion:
    """一次检索式建议（须经人确认后才写入检索框）。"""

    suggested_query: str
    blocks: list[QueryBlock]
    unmatched_terms: list[str]
    generated_at: datetime
    study_types: list[str] = field(default_factory=list)

    def to_blocks_payload(self) -> list[dict]:
        return [block.to_dict() for block in self.blocks]


def has_latin_letters(text: str) -> bool:
    """是否含拉丁字母（无拉丁字母时不请求 MeSH，避免空跑）。"""
    return bool(_LATIN_RE.search(text))


def split_pico_concepts(value: str | list[str] | None) -> list[str]:
    """把一个 PICO 格子拆成多个概念（分号或换行）；逗号不拆，以免拆开 MeSH 倒置词。"""
    if value is None:
        return []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(split_pico_concepts(str(item)))
        return items
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[;\n；]+", text) if part.strip()]


def pubmed_quote(term: str) -> str:
    """需要时给检索词加引号。"""
    cleaned = " ".join(term.split()).replace('"', "")
    if not cleaned:
        return cleaned
    upper_tokens = set(cleaned.upper().split())
    if _QUOTE_NEEDED_RE.search(cleaned) or upper_tokens & {"AND", "OR", "NOT"}:
        return f'"{cleaned}"'
    return cleaned


def _unmatched_result(term: str) -> MeshLookupResult:
    return MeshLookupResult(query=term, matched=False)


def _lookup_or_skip(
    term: str,
    lookup_mesh: Callable[[str], MeshLookupResult] | None,
) -> MeshLookupResult:
    if not has_latin_letters(term):
        return _unmatched_result(term)
    if lookup_mesh is None:
        return _unmatched_result(term)
    try:
        return lookup_mesh(term)
    except PubMedError:
        # 单个概念查词失败时仍用原文 [Title/Abstract]，不中断整条建议
        return _unmatched_result(term)


def build_concept_clause(original: str, mesh: MeshLookupResult) -> tuple[str, list[str]]:
    """拼单个概念的 (MeSH OR 入口词[tiab] OR 原文[tiab])。"""
    pieces: list[str] = []
    terms_used: list[str] = []
    if mesh.matched and mesh.descriptor:
        tagged = f"{pubmed_quote(mesh.descriptor)}[{mesh.field_tag}]"
        pieces.append(tagged)
        terms_used.append(mesh.descriptor)
        for entry in mesh.entry_terms:
            piece = f"{pubmed_quote(entry)}[Title/Abstract]"
            if piece not in pieces:
                pieces.append(piece)
                terms_used.append(entry)
    original_piece = f"{pubmed_quote(original)}[Title/Abstract]"
    if original_piece not in pieces:
        pieces.append(original_piece)
        if original not in terms_used:
            terms_used.append(original)
    if len(pieces) == 1:
        return pieces[0], terms_used
    return "(" + " OR ".join(pieces) + ")", terms_used


def _pico_block(
    role: str,
    label: str,
    original: str | list[str],
    lookup_mesh: Callable[[str], MeshLookupResult] | None,
) -> QueryBlock | None:
    concepts = split_pico_concepts(original)
    if not concepts:
        return None
    subclauses: list[str] = []
    terms_used: list[str] = []
    unmatched: list[str] = []
    descriptors: list[str] = []
    for concept in concepts:
        mesh = _lookup_or_skip(concept, lookup_mesh)
        clause, used = build_concept_clause(concept, mesh)
        subclauses.append(clause)
        for term in used:
            if term not in terms_used:
                terms_used.append(term)
        if mesh.matched:
            if mesh.descriptor and mesh.descriptor not in descriptors:
                descriptors.append(mesh.descriptor)
        else:
            unmatched.append(concept)
    if len(subclauses) == 1:
        combined = subclauses[0]
    else:
        combined = "(" + " AND ".join(subclauses) + ")"
    display = "; ".join(concepts)
    return QueryBlock(
        role=role,
        label=label,
        original=display,
        mesh_matched=len(unmatched) == 0,
        clause=combined,
        mesh_descriptor="; ".join(descriptors) if descriptors else None,
        terms_used=terms_used,
        unmatched_concepts=unmatched,
    )


def _study_type_block(study_types: list[str]) -> QueryBlock | None:
    valid = [key for key in study_types if key in STUDY_TYPE_OPTIONS]
    if not valid:
        return None
    clauses = [STUDY_TYPE_OPTIONS[key][1] for key in valid]
    labels = [STUDY_TYPE_OPTIONS[key][0] for key in valid]
    clause = clauses[0] if len(clauses) == 1 else "(" + " OR ".join(clauses) + ")"
    return QueryBlock(
        role="study_type",
        label="研究类型",
        original="、".join(labels),
        mesh_matched=True,
        clause=clause,
        mesh_descriptor=None,
        terms_used=labels,
    )


def _unmatched_from_blocks(blocks: list[QueryBlock]) -> list[str]:
    """收集未匹配 MeSH 的概念（多概念时逐项列出）。"""
    unmatched: list[str] = []
    for block in blocks:
        if block.role == "study_type":
            continue
        if block.unmatched_concepts:
            unmatched.extend(block.unmatched_concepts)
        elif not block.mesh_matched and block.original:
            unmatched.append(block.original)
    return unmatched


def suggest_query(
    *,
    population: str | list[str] = "",
    intervention: str | list[str] = "",
    comparator: str | list[str] = "",
    outcome: str | list[str] = "",
    study_types: list[str] | None = None,
    research_question: str = "",
    lookup_mesh: Callable[[str], MeshLookupResult] | None = None,
) -> QuerySuggestion:
    """由 PICO / 研究问题拼建议检索式。lookup_mesh 为空时不访问网络。"""
    values: dict[str, str | list[str]] = {
        "population": population,
        "intervention": intervention,
        "comparator": comparator,
        "outcome": outcome,
    }
    blocks: list[QueryBlock] = []
    for role, label in PICO_ROLES:
        block = _pico_block(role, label, values[role], lookup_mesh)
        if block is not None:
            blocks.append(block)

    if not blocks and research_question.strip():
        question_block = _pico_block(
            "question",
            "研究问题（作关键词）",
            research_question,
            lookup_mesh,
        )
        if question_block is not None:
            blocks.append(question_block)

    types = [item for item in (study_types or []) if item in STUDY_TYPE_OPTIONS]
    type_block = _study_type_block(types)
    if type_block is not None:
        blocks.append(type_block)

    unmatched = _unmatched_from_blocks(blocks)
    clauses = [block.clause for block in blocks if block.clause]
    suggested = " AND ".join(clauses) if clauses else ""
    return QuerySuggestion(
        suggested_query=suggested,
        blocks=blocks,
        unmatched_terms=unmatched,
        generated_at=datetime.now(timezone.utc),
        study_types=types,
    )


def suggestion_from_payload(
    suggested_query: str | None,
    blocks_payload: list[dict] | None,
    study_types: list[str] | None = None,
    generated_at: datetime | None = None,
) -> QuerySuggestion | None:
    """从已保存的审计字段还原建议（无网络）。"""
    if not suggested_query and not blocks_payload:
        return None
    blocks: list[QueryBlock] = []
    for item in blocks_payload or []:
        blocks.append(
            QueryBlock(
                role=str(item.get("role") or ""),
                label=str(item.get("label") or ""),
                original=str(item.get("original") or ""),
                mesh_matched=bool(item.get("mesh_matched")),
                clause=str(item.get("clause") or ""),
                mesh_descriptor=item.get("mesh_descriptor"),
                terms_used=list(item.get("terms_used") or []),
                unmatched_concepts=list(item.get("unmatched_concepts") or []),
            )
        )
    unmatched = _unmatched_from_blocks(blocks)
    return QuerySuggestion(
        suggested_query=suggested_query or "",
        blocks=blocks,
        unmatched_terms=unmatched,
        generated_at=generated_at or datetime.now(timezone.utc),
        study_types=list(study_types or []),
    )


def format_suggestion_blocks(suggestion: QuerySuggestion) -> str:
    """拼式可视化的 Markdown 文本。"""
    if not suggestion.blocks:
        return "还没有生成检索块。请先填写 PICO 或研究问题。"
    lines: list[str] = []
    for index, block in enumerate(suggestion.blocks):
        if index:
            lines.append("")
            lines.append("**AND**")
            lines.append("")
        concept_count = len(split_pico_concepts(block.original)) if block.original else 0
        if block.mesh_matched:
            status = "已匹配官方 MeSH"
        elif block.unmatched_concepts and concept_count > len(block.unmatched_concepts):
            status = "部分概念未匹配 MeSH，未匹配者仅用题名/摘要关键词"
        else:
            status = "未匹配 MeSH，仅把原文当作题名/摘要关键词"
        lines.append(f"**{block.label}**")
        lines.append(f"- 原文：{block.original}")
        if block.mesh_descriptor:
            lines.append(f"- 官方主题词：{block.mesh_descriptor}")
        lines.append(f"- {status}")
        lines.append(f"- 检索块：`{block.clause}`")
    if suggestion.unmatched_terms:
        lines.append("")
        lines.append("未匹配 MeSH 的词：" + "；".join(suggestion.unmatched_terms))
    return "\n".join(lines)
