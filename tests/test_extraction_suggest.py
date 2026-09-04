"""摘要提取草稿测试（无真实网络）。"""

from src.models.evidence import EvidenceRecord, ExtractionData, ScreeningStatus
from src.services.extraction_suggest import (
    PROMPT_VERSION,
    apply_confirmed_draft,
    empty_draft,
    extraction_ai_entries,
    fields_complete,
    incomplete_included_records,
    parse_extraction_payload,
    suggest_extraction,
)


def test_parse_cate_payload_keeps_zero_and_null():
    draft = parse_extraction_payload(
        {
            "e1": 0,
            "n1": "40",
            "e2": 24,
            "n2": 37,
            "quote": "0/40 vs 24/37 died",
            "notes": "死亡",
        },
        pmid="1",
        datatype="CATE",
        model="deepseek-v4-flash",
    )
    assert draft.e1 == 0
    assert draft.n1 == 40
    assert draft.e2 == 24
    assert draft.n2 == 37
    assert draft.has_any_number() is True
    assert fields_complete(draft.to_extraction_data(), "CATE") is True


def test_parse_missing_numbers_stay_none():
    draft = parse_extraction_payload(
        {"e1": None, "n1": 10, "e2": "", "n2": "n/a", "notes": "人数不全"},
        pmid="2",
        datatype="CATE",
    )
    assert draft.e1 is None
    assert draft.n1 == 10
    assert draft.e2 is None
    assert draft.n2 is None
    assert fields_complete(draft.to_extraction_data(), "CATE") is False


def test_parse_rejects_negative_and_bool():
    draft = parse_extraction_payload(
        {"e1": True, "n1": -1, "e2": 1.5, "n2": 10},
        pmid="3",
        datatype="CATE",
    )
    assert draft.e1 is None
    assert draft.n1 is None
    assert draft.e2 is None
    assert draft.n2 == 10


def test_no_abstract_skips_model():
    called: list = []

    def fake_complete(messages):
        called.append(messages)
        return {"e1": 1, "n1": 10, "e2": 1, "n2": 10}

    record = EvidenceRecord(pmid="9", title="无摘要", abstract=None)
    draft = suggest_extraction(
        pmid=record.pmid,
        title=record.title,
        abstract=record.abstract,
        datatype="CATE",
        complete_json=fake_complete,
        model="deepseek-v4-flash",
    )
    assert called == []
    assert record.extraction is None
    assert draft.has_any_number() is False
    assert "没有摘要也没有全文" in draft.notes


def test_suggest_uses_injected_complete_json_and_does_not_write():
    def fake_complete(messages):
        assert any("system" == item["role"] for item in messages)
        return {
            "e1": 15,
            "n1": 40,
            "e2": 24,
            "n2": 37,
            "quote": "15/40 vs 24/37",
            "notes": "主要结局为死亡",
        }

    record = EvidenceRecord(
        pmid="111",
        title="Fang 2015",
        abstract="Death occurred in 15 of 40 vs 24 of 37.",
        screening_status=ScreeningStatus.INCLUDE,
    )
    draft = suggest_extraction(
        pmid=record.pmid,
        title=record.title,
        abstract=record.abstract,
        datatype="CATE",
        outcome_hint="mortality",
        complete_json=fake_complete,
        model="deepseek-v4-flash",
    )
    assert record.extraction is None
    assert draft.e1 == 15
    assert draft.quote.startswith("15/40")
    assert draft.model == "deepseek-v4-flash"
    assert draft.prompt_version == PROMPT_VERSION


def test_empty_payload_is_not_complete():
    def fake_complete(_messages):
        return {"e1": None, "n1": None, "e2": None, "n2": None, "quote": "", "notes": ""}

    draft = suggest_extraction(
        pmid="8",
        title="T",
        abstract="This review discusses metformin.",
        datatype="CATE",
        complete_json=fake_complete,
    )
    assert draft.has_any_number() is False
    assert "没有找到" in draft.notes or draft.notes == ""


def test_confirm_writes_extraction_without_touching_pubmed_fields():
    record = EvidenceRecord(
        pmid="111",
        title="Keep title",
        abstract="Keep abstract",
        screening_status=ScreeningStatus.INCLUDE,
    )
    draft = parse_extraction_payload(
        {"e1": 15, "n1": 40, "e2": 24, "n2": 37, "quote": "15/40 vs 24/37"},
        pmid="111",
        datatype="CATE",
        model="deepseek-v4-flash",
    )
    updated = apply_confirmed_draft([record], draft, study_label="Fang 2015")
    assert updated[0].title == "Keep title"
    assert updated[0].abstract == "Keep abstract"
    assert updated[0].extraction is not None
    assert updated[0].extraction.e1 == 15
    assert updated[0].extraction.ai_used is True
    assert updated[0].extraction.ai_model == "deepseek-v4-flash"
    assert updated[0].extraction.ai_draft["n1"] == 40
    assert fields_complete(updated[0].extraction, "CATE") is True
    assert record.extraction is None


def test_incomplete_included_skips_complete_and_excluded():
    records = [
        EvidenceRecord(
            pmid="1",
            title="A",
            screening_status=ScreeningStatus.INCLUDE,
            extraction=ExtractionData(e1=1, n1=2, e2=1, n2=2),
        ),
        EvidenceRecord(
            pmid="2",
            title="B",
            screening_status=ScreeningStatus.INCLUDE,
        ),
        EvidenceRecord(
            pmid="3",
            title="C",
            screening_status=ScreeningStatus.EXCLUDE,
        ),
    ]
    candidates = incomplete_included_records(records, "CATE")
    assert [item.pmid for item in candidates] == ["2"]


def test_empty_draft_has_no_numbers():
    draft = empty_draft("1", "CATE", "没有摘要")
    assert draft.has_any_number() is False


def test_extraction_ai_entries_only_confirmed():
    records = [
        EvidenceRecord(
            pmid="1",
            title="A",
            extraction=ExtractionData(e1=1, n1=2, e2=1, n2=2, ai_used=True, ai_model="m"),
        ),
        EvidenceRecord(
            pmid="2",
            title="B",
            extraction=ExtractionData(e1=1, n1=2, e2=1, n2=2),
        ),
    ]
    entries = extraction_ai_entries(records)
    assert len(entries) == 1
    assert entries[0]["pmid"] == "1"
    assert entries[0]["ai_model"] == "m"


def test_suggest_from_fulltext_uses_body_not_abstract_only():
    seen: list[str] = []

    def fake_complete(messages):
        content = messages[-1]["content"]
        seen.append(content)
        return {
            "e1": 15,
            "n1": 40,
            "e2": 24,
            "n2": 37,
            "quote": "15 of 40 versus 24 of 37",
            "notes": "来自结果段",
        }

    draft = suggest_extraction(
        pmid="111",
        title="Fang 2015",
        abstract="No numbers here.",
        datatype="CATE",
        full_text="Events were 15 of 40 versus 24 of 37 in the primary outcome.",
        text_source="pdf_upload",
        complete_json=fake_complete,
        model="deepseek-v4-flash",
    )
    assert draft.e1 == 15
    assert draft.text_source == "pdf_upload"
    assert draft.to_draft_dict()["text_source"] == "pdf_upload"
    assert "全文：" in seen[0]
    assert "15 of 40" in seen[0]


def test_suggest_fulltext_without_body_or_abstract():
    called: list = []

    def fake_complete(messages):
        called.append(messages)
        return {"e1": 1, "n1": 10, "e2": 1, "n2": 10}

    draft = suggest_extraction(
        pmid="9",
        title="空",
        abstract=None,
        datatype="CATE",
        full_text=None,
        complete_json=fake_complete,
    )
    assert called == []
    assert draft.has_any_number() is False
    assert "没有摘要也没有全文" in draft.notes
