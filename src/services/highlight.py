"""筛选关键词高亮。"""

from __future__ import annotations

import re

from src.services.search import SearchResult

STOPWORDS = {
    "and",
    "or",
    "not",
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "for",
    "to",
    "with",
    "vs",
    "与",
    "或",
    "和",
    "的",
    "及",
}


def extract_keywords(search: SearchResult | None) -> list[str]:
    """从 PICO 与纳入标准提取高亮关键词（简单分词，非 AI）。"""
    if search is None:
        return []
    parts = [
        search.pico_population,
        search.pico_intervention,
        search.pico_comparator,
        search.pico_outcome,
        search.inclusion_criteria,
    ]
    text = " ".join(part for part in parts if part)
    if not text.strip():
        return []
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE)
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        key = token.casefold()
        if len(key) < 3 or key in STOPWORDS or key in seen:
            continue
        seen.add(key)
        keywords.append(token)
    return keywords[:20]


def highlight_text(text: str, keywords: list[str]) -> str:
    """在文本中高亮关键词（Streamlit 安全 HTML）。"""
    if not text or not keywords:
        return text
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for keyword in sorted(keywords, key=len, reverse=True):
        if not keyword:
            continue
        pattern = re.compile(re.escape(keyword), flags=re.IGNORECASE)
        escaped = pattern.sub(
            lambda m: f'<mark style="background:#FFF3B0;padding:0 2px;">{m.group(0)}</mark>',
            escaped,
        )
    return escaped
