"""PubMed 网页链接解析测试。"""

from src.services.pubmed_url import (
    map_sort_to_api,
    parse_pubmed_url,
    suggest_retmax,
)

AUTHOR_STYLE_URL = (
    "https://pubmed.ncbi.nlm.nih.gov/?term=ng%20cheng%20han&sort=date&size=100"
)

TOPIC_URL = (
    "https://pubmed.ncbi.nlm.nih.gov/?term=heart+failure&sort=date&size=50"
)


def test_parse_author_style_url():
    imported = parse_pubmed_url(AUTHOR_STYLE_URL)
    assert imported is not None
    assert imported.term == "ng cheng han"
    assert imported.sort == "date"
    assert imported.size_hint == 100


def test_parse_topic_url():
    imported = parse_pubmed_url(TOPIC_URL)
    assert imported is not None
    assert imported.term == "heart failure"
    assert imported.sort == "date"
    assert imported.size_hint == 50


def test_parse_invalid_url():
    assert parse_pubmed_url("") is None
    assert parse_pubmed_url("https://example.com/?term=test") is None
    assert parse_pubmed_url("https://pubmed.ncbi.nlm.nih.gov/") is None


def test_map_sort_to_api():
    assert map_sort_to_api("date") == "pub_date"
    assert map_sort_to_api(None) is None
    assert map_sort_to_api("relevance") is None


def test_suggest_retmax():
    assert suggest_retmax(100) == 100
    assert suggest_retmax(50) == 50
    assert suggest_retmax(30) == 20
    assert suggest_retmax(150) == 100
    assert suggest_retmax(200) == 200
    assert suggest_retmax(600) == 500
    assert suggest_retmax(None) == 10
