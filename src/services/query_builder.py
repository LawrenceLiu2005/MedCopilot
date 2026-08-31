"""检索式辅助：作者字段包装与 PubMed 语法检测。"""

from __future__ import annotations

import re

_BOOL_PATTERN = re.compile(r"\b(AND|OR|NOT)\b", re.IGNORECASE)
_FIELD_TAG_PATTERN = re.compile(r"\[[^\]]+\]")


def has_pubmed_syntax(query: str) -> bool:
    """检索式是否含 PubMed 字段标签或布尔运算符。"""
    text = query.strip()
    if not text:
        return False
    if _FIELD_TAG_PATTERN.search(text):
        return True
    return bool(_BOOL_PATTERN.search(text))


def can_wrap_author_field(query: str) -> bool:
    """纯文本且无 PubMed 语法时，才允许包装为 [Author]。"""
    text = query.strip()
    if not text:
        return False
    return not has_pubmed_syntax(text)


def wrap_author_query(name: str) -> str:
    """将姓名包装为 PubMed 作者字段检索式。"""
    cleaned = " ".join(name.strip().split())
    return f'"{cleaned}"[Author]'


def build_effective_query(raw_query: str, *, author_field: bool) -> str:
    """根据是否限定作者字段，生成最终发送给 PubMed 的检索式。"""
    query = raw_query.strip()
    if not query:
        return query
    if author_field and can_wrap_author_field(query):
        return wrap_author_query(query)
    return query


def author_wrap_applied(raw_query: str, *, author_field: bool) -> bool:
    """作者字段包装是否已生效。"""
    query = raw_query.strip()
    if not query or not author_field:
        return False
    return build_effective_query(query, author_field=True) != query
