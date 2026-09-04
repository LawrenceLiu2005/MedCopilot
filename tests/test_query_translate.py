"""检索式跨库翻译测试。"""

from src.services.query_translate import translate_pubmed_query, translation_text


def test_translate_title_abstract_query():
    items = translate_pubmed_query(
        '("digital health"[Title/Abstract]) AND ("privacy"[Title/Abstract])'
    )
    wos = translation_text(items, "wos")
    ebsco = translation_text(items, "ebscohost")
    assert wos is not None
    assert "digital health" in wos
    assert ebsco is not None
    assert "digital health" in ebsco


def test_translate_empty_query():
    assert translate_pubmed_query("   ") == []


def test_translate_mesh_wos_fails_ebsco_ok():
    items = translate_pubmed_query("(diabetes[MeSH]) AND metformin[Title/Abstract]")
    wos = next(item for item in items if item.platform == "wos")
    ebsco = next(item for item in items if item.platform == "ebscohost")
    assert wos.query is None
    assert wos.error
    assert "MeSH" in wos.error
    assert ebsco.query is not None
    assert "diabetes" in ebsco.query


def test_translate_unbalanced_parentheses():
    items = translate_pubmed_query("diabetes AND (metformin OR insulin")
    assert items
    assert all(item.query is None for item in items)
    assert any("括号" in (item.error or "") or "语法" in (item.error or "") for item in items)
