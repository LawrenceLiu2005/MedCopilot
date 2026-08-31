"""初筛逻辑测试。"""

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.screening import (
    bulk_update_records,
    count_by_status,
    dedupe_records,
    filter_by_publication_types,
    filter_by_status,
    flag_potential_duplicates,
    format_exclusion_reason,
    parse_exclusion_reason,
    screening_progress,
    update_record,
)


def _record(pmid: str, doi: str | None = None, title: str = "T") -> EvidenceRecord:
    return EvidenceRecord(pmid=pmid, doi=doi, title=title)


def _record_with_types(pmid: str, types: list[str]) -> EvidenceRecord:
    return EvidenceRecord(pmid=pmid, title="T", publication_types=types)


def test_dedupe_by_pmid_then_doi():
    records = [
        _record("1", "10.1/a"),
        _record("1", "10.1/b"),
        _record("2", "10.1/a"),
        _record("3", "10.1/c"),
    ]
    deduped = dedupe_records(records)
    assert [r.pmid for r in deduped.records] == ["1", "3"]
    assert deduped.removed_count == 2
    assert deduped.removed_pmids == ["1", "2"]


def test_count_and_filter():
    records = [
        _record("1"),
        EvidenceRecord(pmid="2", title="B", screening_status=ScreeningStatus.INCLUDE),
    ]
    counts = count_by_status(records)
    assert counts["Total"] == 2
    assert counts["Include"] == 1
    assert len(filter_by_status(records, ScreeningStatus.INCLUDE)) == 1


def test_update_record_does_not_change_title():
    records = [_record("1", title="原始标题")]
    updated = update_record(
        records,
        "1",
        ScreeningStatus.EXCLUDE,
        exclusion_reason="Not relevant",
        notes="测试",
    )
    assert updated[0].title == "原始标题"
    assert updated[0].screening_status == ScreeningStatus.EXCLUDE
    assert updated[0].exclusion_reason == "Not relevant"
    assert updated[0].notes == "测试"


def test_flag_potential_duplicates_marks_similar_titles_without_removing():
    records = [
        _record("1", title="Metformin for Type 2 Diabetes: A Randomized Trial"),
        _record("2", title="Metformin for Type 2 Diabetes - A Randomized Trial"),
        _record("3", title="Completely Different Topic"),
    ]
    flagged = flag_potential_duplicates(records)
    assert len(flagged) == 3
    by_pmid = {record.pmid: record for record in flagged}
    assert by_pmid["1"].potential_duplicate is True
    assert by_pmid["2"].potential_duplicate is True
    assert by_pmid["3"].potential_duplicate is False


def test_parse_exclusion_reason_empty():
    assert parse_exclusion_reason(None) == ("", "")
    assert parse_exclusion_reason("") == ("", "")


def test_update_record_clears_exclusion_reason_when_not_exclude():
    records = [
        EvidenceRecord(
            pmid="1",
            title="T",
            screening_status=ScreeningStatus.EXCLUDE,
            exclusion_reason="Animal study",
        )
    ]
    updated = update_record(records, "1", ScreeningStatus.INCLUDE, notes="maybe")
    assert updated[0].screening_status == ScreeningStatus.INCLUDE
    assert updated[0].exclusion_reason is None


def test_dedupe_doi_is_case_insensitive():
    records = [
        _record("1", "10.1000/ABC"),
        _record("2", "10.1000/abc"),
    ]
    deduped = dedupe_records(records)
    assert [r.pmid for r in deduped.records] == ["1"]
    assert deduped.removed_pmids == ["2"]


def test_other_exclusion_reason_with_custom_detail():
    records = [_record("1")]
    updated = update_record(
        records,
        "1",
        ScreeningStatus.EXCLUDE,
        exclusion_reason="Other: 非人类研究",
        notes="",
    )
    assert updated[0].exclusion_reason == "Other: 非人类研究"
    preset, detail = parse_exclusion_reason(updated[0].exclusion_reason)
    assert preset == "Other"
    assert detail == "非人类研究"
    assert format_exclusion_reason("Other", "非人类研究") == "Other: 非人类研究"


def test_filter_by_publication_types():
    records = [
        _record_with_types("1", ["Meta-Analysis"]),
        _record_with_types("2", ["Journal Article"]),
        _record_with_types("3", ["Meta-Analysis", "Review"]),
    ]
    filtered = filter_by_publication_types(records, ["Meta-Analysis"])
    assert [r.pmid for r in filtered] == ["1", "3"]
    assert filter_by_publication_types(records, None) == records
    assert filter_by_publication_types(records, []) == records


def test_screening_progress():
    records = [
        _record("1"),
        EvidenceRecord(pmid="2", title="B", screening_status=ScreeningStatus.INCLUDE),
    ]
    assert screening_progress(records) == (1, 2)


def test_bulk_update_records():
    records = [
        _record("1"),
        _record("2"),
        _record("3"),
    ]
    updated = bulk_update_records(records, {"1", "2"}, ScreeningStatus.INCLUDE)
    assert updated[0].screening_status == ScreeningStatus.INCLUDE
    assert updated[1].screening_status == ScreeningStatus.INCLUDE
    assert updated[2].screening_status == ScreeningStatus.UNSCREENED

    excluded = bulk_update_records(
        updated, {"3"}, ScreeningStatus.EXCLUDE, exclusion_reason="Animal study"
    )
    assert excluded[2].screening_status == ScreeningStatus.EXCLUDE
    assert excluded[2].exclusion_reason == "Animal study"
    assert excluded[0].exclusion_reason is None
