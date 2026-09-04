"""检索式建议测试（无网络）。"""

from src.clients.pubmed import MeshLookupResult, PubMedError
from src.services.query_suggest import (
    format_suggestion_blocks,
    has_latin_letters,
    pubmed_quote,
    split_pico_concepts,
    suggest_query,
)


def _lookup(term: str) -> MeshLookupResult:
    lowered = term.casefold()
    if lowered == "metformin":
        return MeshLookupResult(
            query=term,
            matched=True,
            descriptor="Metformin",
            mesh_id="D008687",
            entry_terms=("dimethylbiguanide",),
            field_tag="MeSH Terms",
        )
    if "diabetes" in lowered:
        return MeshLookupResult(
            query=term,
            matched=True,
            descriptor="Diabetes Mellitus, Type 2",
            mesh_id="D003924",
            entry_terms=("Type 2 Diabetes",),
            field_tag="MeSH Terms",
        )
    return MeshLookupResult(query=term, matched=False)


def test_chinese_only_becomes_title_abstract():
    suggestion = suggest_query(
        population="二型糖尿病",
        intervention="二甲双胍",
        lookup_mesh=_lookup,
    )
    assert "[Title/Abstract]" in suggestion.suggested_query
    assert "[MeSH Terms]" not in suggestion.suggested_query
    assert "二型糖尿病" in suggestion.unmatched_terms
    assert "二甲双胍" in suggestion.unmatched_terms
    assert "AND" in suggestion.suggested_query


def test_english_pico_uses_mesh_and_study_type():
    suggestion = suggest_query(
        population="type 2 diabetes",
        intervention="metformin",
        study_types=["rct"],
        lookup_mesh=_lookup,
    )
    assert '"Diabetes Mellitus, Type 2"[MeSH Terms]' in suggestion.suggested_query
    assert "Metformin[MeSH Terms]" in suggestion.suggested_query
    assert "Randomized Controlled Trial" in suggestion.suggested_query
    assert "type 2 diabetes" not in suggestion.unmatched_terms
    assert "metformin" not in suggestion.unmatched_terms


def test_empty_comparator_omitted():
    suggestion = suggest_query(
        population="type 2 diabetes",
        intervention="metformin",
        comparator="",
        outcome="",
        lookup_mesh=_lookup,
    )
    roles = [block.role for block in suggestion.blocks]
    assert "comparator" not in roles
    assert "outcome" not in roles


def test_research_question_fallback_when_pico_empty():
    suggestion = suggest_query(
        research_question="二甲双胍 糖尿病",
        lookup_mesh=_lookup,
    )
    assert suggestion.blocks[0].role == "question"
    assert "二甲双胍" in suggestion.suggested_query
    assert suggestion.suggested_query.count("AND") == 0


def test_does_not_call_lookup_for_chinese(monkeypatch):
    calls: list[str] = []

    def tracking_lookup(term: str) -> MeshLookupResult:
        calls.append(term)
        return MeshLookupResult(query=term, matched=False)

    suggest_query(population="糖尿病成人", lookup_mesh=tracking_lookup)
    assert calls == []


def test_has_latin_letters():
    assert has_latin_letters("metformin")
    assert not has_latin_letters("二甲双胍")


def test_pubmed_quote_phrases():
    assert pubmed_quote("metformin") == "metformin"
    assert pubmed_quote("type 2 diabetes") == '"type 2 diabetes"'


def test_format_suggestion_blocks_mentions_unmatched():
    suggestion = suggest_query(population="二甲双胍", lookup_mesh=_lookup)
    text = format_suggestion_blocks(suggestion)
    assert "未匹配" in text
    assert "二甲双胍" in text


def test_lookup_error_falls_back_to_title_abstract():
    def boom(_term: str):
        raise PubMedError("MeSH XML 解析失败。")

    suggestion = suggest_query(population="metformin", lookup_mesh=boom)
    assert suggestion.blocks[0].mesh_matched is False
    assert "metformin[Title/Abstract]" in suggestion.suggested_query
    assert "[MeSH Terms]" not in suggestion.suggested_query


def test_split_pico_concepts_semicolon_not_comma():
    assert split_pico_concepts("hepatocellular carcinoma; diabetes mellitus") == [
        "hepatocellular carcinoma",
        "diabetes mellitus",
    ]
    assert split_pico_concepts("Diabetes Mellitus, Type 2") == ["Diabetes Mellitus, Type 2"]


def test_multiple_population_concepts_are_anded():
    suggestion = suggest_query(
        population="hepatocellular carcinoma; type 2 diabetes",
        intervention="metformin",
        lookup_mesh=_lookup,
    )
    assert suggestion.suggested_query.count(" AND ") >= 2
    assert "Diabetes Mellitus, Type 2" in suggestion.suggested_query
    assert "Metformin[MeSH Terms]" in suggestion.suggested_query
    assert "hepatocellular carcinoma" in suggestion.unmatched_terms
    assert "type 2 diabetes" not in suggestion.unmatched_terms
