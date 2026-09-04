"""将 PubMed 检索式翻译为其他数据库语法（整合 search-query，仅供复制）。"""

from __future__ import annotations

from dataclasses import dataclass
import re

from search_query.parser import parse

TRANSLATE_TARGETS: tuple[tuple[str, str], ...] = (
    ("wos", "Web of Science"),
    ("ebscohost", "EBSCOHost"),
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class QueryTranslation:
    """单条跨库翻译结果。"""

    platform: str
    label: str
    query: str | None
    error: str | None


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).strip()


def _exception_text(exc: BaseException) -> str:
    return " ".join(part for part in (type(exc).__name__, str(exc)) if part).strip()


def _humanize_error(raw: str, *, label: str) -> str:
    """把库报错改成白话，不编造翻译结果。"""
    text = _strip_ansi(raw)
    lowered = text.lower()
    if "mesh" in lowered and "not supported" in lowered:
        return (
            f"{label} 不支持 MeSH 字段，无法自动翻译。"
            "请人工改写，或先把 [MeSH] 改成题名/摘要字段后再试。"
        )
    if (
        "unbalanced" in lowered
        or "parenthesis" in lowered
        or "querysyntaxerror" in lowered
    ):
        return "检索式括号不配对或语法有误，无法翻译。"
    if "not implemented" in lowered:
        return f"当前不支持翻译到 {label}。"
    if "string index out of range" in lowered:
        return "检索式为空，无法翻译。"
    if text:
        return f"翻译到 {label} 失败：{text}"
    return f"翻译到 {label} 失败。"


def translate_pubmed_query(query: str) -> list[QueryTranslation]:
    """把 PubMed 检索式分别译成 WOS / EBSCO；失败则记录原因，不假装成功。"""
    stripped = query.strip()
    if not stripped:
        return []

    parsed = None
    parse_error: str | None = None
    try:
        parsed = parse(stripped, platform="pubmed")
    except Exception as exc:
        parse_error = _humanize_error(_exception_text(exc), label="其他数据库")

    results: list[QueryTranslation] = []
    for platform, label in TRANSLATE_TARGETS:
        if parsed is None:
            results.append(
                QueryTranslation(
                    platform=platform,
                    label=label,
                    query=None,
                    error=parse_error,
                )
            )
            continue
        try:
            translated = parsed.translate(target_syntax=platform)
            text = translated.to_string().strip() if translated is not None else ""
            if not text:
                results.append(
                    QueryTranslation(
                        platform=platform,
                        label=label,
                        query=None,
                        error=f"翻译到 {label} 未得到有效检索式。",
                    )
                )
                continue
            results.append(
                QueryTranslation(platform=platform, label=label, query=text, error=None)
            )
        except Exception as exc:
            results.append(
                QueryTranslation(
                    platform=platform,
                    label=label,
                    query=None,
                    error=_humanize_error(_exception_text(exc), label=label),
                )
            )
    return results


def translation_text(items: list[QueryTranslation], platform: str) -> str | None:
    """取出某一平台的成功翻译文本；失败则 None。"""
    for item in items:
        if item.platform == platform and item.query:
            return item.query
    return None
