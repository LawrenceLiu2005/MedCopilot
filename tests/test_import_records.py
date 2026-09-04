"""导入记录测试。"""

from src.services.import_records import parse_pmid_list, parse_ris_text


def test_parse_pmid_list():
    assert parse_pmid_list("123, 456\n789") == ["123", "456", "789"]


def test_parse_ris_text_with_pmid():
    ris = """TY  - JOUR
AU  - Smith, John
TI  - Test title
AN  - 12345678
ER  -

"""
    records, missing = parse_ris_text(ris)
    assert len(records) == 1
    assert records[0].pmid == "12345678"
    assert records[0].title == "Test title"
    assert missing == []
