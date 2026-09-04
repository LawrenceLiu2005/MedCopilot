"""PythonMeta 包装与提取完整性测试。"""

import pytest

from src.models.evidence import EvidenceRecord, ExtractionData, ScreeningStatus
from src.services.meta_analysis import (
    PYTHONMETA_SAMPLE_CATE,
    extraction_is_complete,
    extraction_to_line,
    run_meta_analysis,
    run_meta_from_lines,
    update_extraction,
)


def test_extraction_zero_is_complete_empty_is_not():
    filled = ExtractionData(e1=0, n1=10, e2=1, n2=10)
    assert extraction_is_complete(filled, "CATE") is True
    empty = ExtractionData(e1=None, n1=10, e2=1, n2=10)
    assert extraction_is_complete(empty, "CATE") is False
    assert extraction_is_complete(None, "CATE") is False


def test_incomplete_included_study_is_skipped():
    records = [
        EvidenceRecord(
            pmid="1",
            title="A",
            screening_status=ScreeningStatus.INCLUDE,
            extraction=ExtractionData(e1=15, n1=40, e2=24, n2=37, study_label="Fang 2015"),
        ),
        EvidenceRecord(
            pmid="2",
            title="B",
            screening_status=ScreeningStatus.INCLUDE,
            extraction=ExtractionData(e1=10, n1=40, e2=18, n2=35, study_label="Gong 2012"),
        ),
        EvidenceRecord(
            pmid="3",
            title="C",
            screening_status=ScreeningStatus.INCLUDE,
            extraction=None,
        ),
        EvidenceRecord(
            pmid="4",
            title="D",
            screening_status=ScreeningStatus.EXCLUDE,
            extraction=ExtractionData(e1=1, n1=2, e2=1, n2=2, study_label="Skip"),
        ),
    ]
    result = run_meta_analysis(
        records,
        datatype="CATE",
        models="Fixed",
        algorithm="MH",
        effect="RR",
        draw_plots=False,
    )
    assert result.n_studies == 2
    assert result.skipped_pmids == ["3"]
    assert result.pooled_effect is not None
    assert result.i2 is None or 0 <= result.i2 <= 100


def test_pythonmeta_sample_cate_regression():
    result = run_meta_from_lines(
        PYTHONMETA_SAMPLE_CATE,
        datatype="CATE",
        models="Fixed",
        algorithm="MH",
        effect="RR",
        draw_plots=False,
    )
    assert result.n_studies == 5
    assert result.pooled_effect is not None
    assert result.ci_low is not None
    assert result.ci_high is not None
    assert result.ci_low <= result.pooled_effect <= result.ci_high
    assert result.i2 is None or 0 <= result.i2 <= 100
    assert "异质性" in result.text_table


def test_need_two_complete_studies():
    records = [
        EvidenceRecord(
            pmid="1",
            title="A",
            screening_status=ScreeningStatus.INCLUDE,
            extraction=ExtractionData(e1=1, n1=10, e2=2, n2=10, study_label="Only"),
        )
    ]
    with pytest.raises(ValueError, match="至少需要 2"):
        run_meta_analysis(
            records,
            datatype="CATE",
            models="Fixed",
            algorithm="MH",
            effect="RR",
            draw_plots=False,
        )


def test_update_extraction_does_not_touch_pubmed_fields():
    record = EvidenceRecord(pmid="1", title="Keep", abstract="Abs")
    updated = update_extraction(
        [record],
        "1",
        ExtractionData(e1=1, n1=2, e2=3, n2=4),
    )
    assert updated[0].title == "Keep"
    assert updated[0].abstract == "Abs"
    assert updated[0].extraction is not None
    assert updated[0].extraction.e1 == 1


def test_extraction_to_line_strips_comma_in_label():
    record = EvidenceRecord(
        pmid="1",
        title="T",
        screening_status=ScreeningStatus.INCLUDE,
        extraction=ExtractionData(
            study_label="Fang, 2015",
            e1=1,
            n1=2,
            e2=1,
            n2=2,
        ),
    )
    line = extraction_to_line(record, "CATE")
    assert line is not None
    assert line.count(",") == 4
    assert "Fang" in line
