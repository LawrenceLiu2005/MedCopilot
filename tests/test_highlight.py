"""关键词高亮测试。"""

from datetime import datetime, timezone

from src.services.highlight import extract_keywords, highlight_text
from src.services.search import SearchResult


def test_extract_keywords_from_pico():
    search = SearchResult(
        search_id="x",
        research_question="",
        query="q",
        year_from=None,
        year_to=None,
        retmax=1,
        total_hits=1,
        records=[],
        executed_at=datetime.now(timezone.utc),
        pico_intervention="metformin therapy",
        inclusion_criteria="type 2 diabetes adults",
    )
    keywords = extract_keywords(search)
    assert "metformin" in [k.lower() for k in keywords]


def test_highlight_text():
    html = highlight_text("Metformin in diabetes", ["metformin"])
    assert "<mark" in html
