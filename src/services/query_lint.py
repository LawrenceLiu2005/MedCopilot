"""检索式语法检查（整合 search-query）。"""

from __future__ import annotations

from dataclasses import dataclass

import search_query.linter as sq_linter


@dataclass
class QueryLintIssue:
    """单条检索式 lint 提示。"""

    code: str
    label: str
    message: str
    is_fatal: bool


def lint_pubmed_query(query: str) -> list[QueryLintIssue]:
    """对 PubMed 检索式做 lint；空检索式返回空列表。"""
    stripped = query.strip()
    if not stripped:
        return []
    try:
        raw_issues = sq_linter.lint_query_string(stripped, platform="pubmed")
    except Exception:
        return []
    issues: list[QueryLintIssue] = []
    for item in raw_issues:
        issues.append(
            QueryLintIssue(
                code=str(item.get("code", "")),
                label=str(item.get("label", "")),
                message=str(item.get("message", "")),
                is_fatal=bool(item.get("is_fatal", False)),
            )
        )
    return issues
