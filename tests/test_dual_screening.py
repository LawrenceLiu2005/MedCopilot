"""双人初筛与 Cohen's Kappa 测试。"""

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.dual_screening import (
    apply_reviewer2_status,
    cohen_kappa,
    compute_agreement,
    disagreements,
    parse_reviewer2_csv,
    parse_screening_status,
    reviewer2_template_csv,
)


def _record(pmid: str, status: ScreeningStatus) -> EvidenceRecord:
    return EvidenceRecord(pmid=pmid, title=f"T{pmid}", screening_status=status)


def test_parse_status_aliases():
    assert parse_screening_status("纳入") == ScreeningStatus.INCLUDE
    assert parse_screening_status("Exclude") == ScreeningStatus.EXCLUDE
    assert parse_screening_status("待定") == ScreeningStatus.MAYBE
    assert parse_screening_status("nonsense") is None


def test_parse_reviewer2_csv_prefers_reviewer2_column():
    csv_text = (
        "PMID,Screening Status,Reviewer 2 Status\n"
        "1,Include,Exclude\n"
        "2,Include,Include\n"
    )
    mapping, invalid = parse_reviewer2_csv(csv_text)
    assert invalid == []
    assert mapping["1"] == ScreeningStatus.EXCLUDE
    assert mapping["2"] == ScreeningStatus.INCLUDE


def test_parse_reviewer2_csv_falls_back_when_r2_empty():
    csv_text = (
        "PMID,Screening Status,Reviewer 2 Status\n"
        "1,Exclude,\n"
        "2,Include,\n"
    )
    mapping, invalid = parse_reviewer2_csv(csv_text)
    assert invalid == []
    assert mapping["1"] == ScreeningStatus.EXCLUDE
    assert mapping["2"] == ScreeningStatus.INCLUDE


def test_parse_reviewer2_csv_chinese_status():
    csv_text = "PMID,状态\n1,纳入\n2,排除\n"
    mapping, invalid = parse_reviewer2_csv(csv_text)
    assert invalid == []
    assert mapping["1"] == ScreeningStatus.INCLUDE
    assert mapping["2"] == ScreeningStatus.EXCLUDE


def test_apply_reviewer2_does_not_change_reviewer1():
    records = [_record("1", ScreeningStatus.INCLUDE), _record("2", ScreeningStatus.EXCLUDE)]
    updated, summary = apply_reviewer2_status(
        records,
        {"1": ScreeningStatus.EXCLUDE, "9": ScreeningStatus.INCLUDE},
    )
    assert summary.applied == 1
    assert summary.skipped_unknown_pmid == ["9"]
    assert updated[0].screening_status == ScreeningStatus.INCLUDE
    assert updated[0].reviewer2_status == ScreeningStatus.EXCLUDE
    assert updated[0].title == "T1"


def test_cohen_kappa_known_example():
    labels_a = ["Include", "Include", "Exclude", "Exclude", "Include"]
    labels_b = ["Include", "Exclude", "Exclude", "Exclude", "Include"]
    kappa = cohen_kappa(labels_a, labels_b)
    assert kappa is not None
    assert abs(kappa - 0.6153846153846154) < 1e-9


def test_cohen_kappa_perfect_and_empty():
    assert cohen_kappa(["Include", "Exclude"], ["Include", "Exclude"]) == 1.0
    assert cohen_kappa([], []) is None


def test_compute_agreement_and_disagreements():
    records = [
        EvidenceRecord(
            pmid="1",
            title="A",
            screening_status=ScreeningStatus.INCLUDE,
            reviewer2_status=ScreeningStatus.INCLUDE,
        ),
        EvidenceRecord(
            pmid="2",
            title="B",
            screening_status=ScreeningStatus.INCLUDE,
            reviewer2_status=ScreeningStatus.EXCLUDE,
        ),
        EvidenceRecord(
            pmid="3",
            title="C",
            screening_status=ScreeningStatus.UNSCREENED,
            reviewer2_status=ScreeningStatus.INCLUDE,
        ),
    ]
    result = compute_agreement(records)
    assert result.n_compared == 2
    assert result.n_agree == 1
    assert result.n_disagree == 1
    assert [r.pmid for r in disagreements(records)] == ["2"]


def test_reviewer2_template_contains_pmid():
    csv_text = reviewer2_template_csv([_record("42", ScreeningStatus.INCLUDE)])
    assert "42" in csv_text
    assert "Reviewer 2 Status" in csv_text
