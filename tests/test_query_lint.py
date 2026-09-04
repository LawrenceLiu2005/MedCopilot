"""检索式 lint 测试。"""

from src.services.query_lint import lint_pubmed_query


def test_lint_unbalanced_parentheses():
    issues = lint_pubmed_query("diabetes AND (metformin OR insulin")
    assert any(issue.is_fatal for issue in issues)


def test_lint_valid_query():
    issues = lint_pubmed_query("(diabetes[MeSH]) AND metformin[Title/Abstract]")
    assert issues == []
