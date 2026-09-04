"""白话拆 PICO 测试（无真实网络）。"""

import pytest

from src.clients.deepseek import DeepSeekError
from src.services.pico_extract import (
    accepted_pico_dict,
    extract_pico,
    has_cjk,
    join_concepts,
    needs_pico_extract,
    parse_pico_payload,
)
from src.services.query_suggest import suggest_query
from tests.test_query_suggest import _lookup


def test_has_cjk():
    assert has_cjk("肝癌合并糖尿病")
    assert not has_cjk("hepatocellular carcinoma")


def test_needs_extract_when_question_chinese_and_pico_empty():
    assert needs_pico_extract("肝癌合并糖尿病的病人，想知道用了二甲双胍是否会延长寿命")


def test_needs_extract_skips_when_pico_filled():
    assert not needs_pico_extract(
        "肝癌合并糖尿病",
        population="hepatocellular carcinoma",
        intervention="metformin",
    )


def test_needs_extract_skips_english_question():
    assert not needs_pico_extract("Does metformin improve survival in HCC?")


def test_parse_pico_payload_coerces_string_and_filters_study_types():
    extraction = parse_pico_payload(
        {
            "population": "hepatocellular carcinoma; diabetes mellitus",
            "intervention": ["metformin"],
            "comparator": None,
            "outcome": "survival",
            "study_types": ["rct", "made-up"],
            "notes": "寿命对应 survival",
        },
        source_text="原句",
        model="deepseek-v4-flash",
    )
    assert extraction.population == ["hepatocellular carcinoma", "diabetes mellitus"]
    assert extraction.intervention == ["metformin"]
    assert extraction.comparator == []
    assert extraction.outcome == ["survival"]
    assert extraction.study_types == ["rct"]
    assert extraction.notes == "寿命对应 survival"
    assert extraction.has_concepts() is True


def test_parse_pico_payload_empty_when_missing_fields():
    extraction = parse_pico_payload({}, source_text="x")
    assert extraction.has_concepts() is False
    assert extraction.study_types == []


def test_join_and_accepted_payload():
    assert join_concepts(["hepatocellular carcinoma", "diabetes mellitus"]) == (
        "hepatocellular carcinoma; diabetes mellitus"
    )
    accepted = accepted_pico_dict(
        population="hepatocellular carcinoma; diabetes mellitus",
        intervention="metformin",
        comparator="",
        outcome="survival",
        study_types=["rct", "nope"],
    )
    assert accepted["study_types"] == ["rct"]
    assert "metformin" in accepted["intervention"]


def test_extract_pico_uses_injected_complete_json():
    def fake_complete(_messages):
        return {
            "population": ["hepatocellular carcinoma", "diabetes mellitus"],
            "intervention": ["metformin"],
            "comparator": [],
            "outcome": ["survival"],
            "study_types": [],
            "notes": "拆分示例",
        }

    extraction = extract_pico(
        "肝癌合并糖尿病的病人，想知道用了二甲双胍是否会延长寿命",
        complete_json=fake_complete,
        model="deepseek-v4-flash",
    )
    suggestion = suggest_query(
        population=extraction.population,
        intervention=extraction.intervention,
        outcome=extraction.outcome,
        lookup_mesh=_lookup,
    )
    assert "AND" in suggestion.suggested_query
    assert "Metformin[MeSH Terms]" in suggestion.suggested_query
    assert extraction.model == "deepseek-v4-flash"


def test_extract_pico_empty_question_raises():
    with pytest.raises(DeepSeekError, match="研究问题为空"):
        extract_pico("  ", complete_json=lambda _m: {})
