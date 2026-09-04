"""人工提取表与 PythonMeta 包装（不从摘要推断数字）。"""

from __future__ import annotations

from dataclasses import dataclass

import matplotlib

try:
    matplotlib.use("Agg")
except Exception:
    pass
import matplotlib.pyplot as plt  # noqa: E402
import PythonMeta as PMA  # noqa: E402

from src.models.evidence import EvidenceRecord, ExtractionData, ScreeningStatus

DATATYPE_CATE = "CATE"
DATATYPE_CONT = "CONT"

EFFECT_OPTIONS = {
    DATATYPE_CATE: ("OR", "RR", "RD"),
    DATATYPE_CONT: ("MD", "SMD"),
}
MODEL_OPTIONS = ("Fixed", "Random")
ALGORITHM_CATE = ("MH", "IV", "Peto")
ALGORITHM_CONT = ("IV",)


def configure_matplotlib_cjk() -> None:
    """设置中文字体，避免方块。"""
    plt.rcParams["font.sans-serif"] = [
        "Heiti TC",
        "PingFang SC",
        "Hiragino Sans GB",
        "Arial Unicode MS",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def default_study_label(record: EvidenceRecord) -> str:
    """默认研究标签：第一作者姓 + 年份；逗号会破坏 PythonMeta 行格式，故去掉。"""
    year = str(record.publication_year) if record.publication_year else ""
    if record.authors:
        last = record.authors[0].replace(",", " ").split()[0]
        label = f"{last} {year}".strip()
        return label or f"PMID{record.pmid}"
    return f"PMID{record.pmid}"


def extraction_is_complete(extraction: ExtractionData | None, datatype: str) -> bool:
    """提取字段是否齐全；缺任一字段则不算完整，0 是合法值。"""
    if extraction is None:
        return False
    if datatype == DATATYPE_CATE:
        return None not in (extraction.e1, extraction.n1, extraction.e2, extraction.n2)
    if datatype == DATATYPE_CONT:
        return None not in (
            extraction.m1,
            extraction.sd1,
            extraction.n1,
            extraction.m2,
            extraction.sd2,
            extraction.n2,
        )
    return False


def included_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    return [r for r in records if r.screening_status == ScreeningStatus.INCLUDE]


def _safe_label(record: EvidenceRecord) -> str:
    extraction = record.extraction
    raw = (extraction.study_label if extraction else None) or default_study_label(record)
    return " ".join(raw.replace(",", " ").split()) or f"PMID{record.pmid}"


def extraction_to_line(record: EvidenceRecord, datatype: str) -> str | None:
    """转为 PythonMeta 输入行；不完整则返回 None。"""
    extraction = record.extraction
    if not extraction_is_complete(extraction, datatype) or extraction is None:
        return None
    label = _safe_label(record)
    if datatype == DATATYPE_CATE:
        return f"{label},{extraction.e1},{extraction.n1},{extraction.e2},{extraction.n2}"
    return (
        f"{label},{extraction.m1},{extraction.sd1},{extraction.n1},"
        f"{extraction.m2},{extraction.sd2},{extraction.n2}"
    )


def update_extraction(
    records: list[EvidenceRecord],
    pmid: str,
    extraction: ExtractionData | None,
) -> list[EvidenceRecord]:
    """更新单篇提取数据，不改 PubMed 字段。"""
    updated: list[EvidenceRecord] = []
    for record in records:
        if record.pmid != pmid:
            updated.append(record)
            continue
        updated.append(record.model_copy(update={"extraction": extraction}))
    return updated


@dataclass
class MetaRunResult:
    """一次 meta 分析的数字结果与图形。"""

    n_studies: int
    skipped_pmids: list[str]
    pooled_effect: float | None
    ci_low: float | None
    ci_high: float | None
    i2: float | None
    q: float | None
    q_p: str | None
    tau2: float | None
    z: float | None
    z_p: str | None
    text_table: str
    forest_fig: object | None
    funnel_fig: object | None
    eggers: tuple | None
    datatype: str
    models: str
    algorithm: str
    effect: str


def _format_results_table(results: list) -> str:
    if not results:
        return ""
    lines = ["研究  n  效应量[95% CI]  权重(%)"]
    total = results[0]
    total_weight = total[2] if total[2] else 1
    for row in results[1:]:
        weight = 100 * (row[2] / total_weight) if total_weight else 0
        lines.append(
            f"{row[0]}  {row[5]}  {row[1]:.2f}[{row[3]:.2f}, {row[4]:.2f}]  {weight:.2f}"
        )
    lines.append(
        f"{total[0]}  {total[5]}  {total[1]:.2f}[{total[3]:.2f}, {total[4]:.2f}]  100"
    )
    i2 = total[9]
    i2_text = f"{round(i2, 2)}%" if isinstance(i2, (int, float)) else str(i2)
    tau = total[12]
    het = f"异质性：Q={total[7]:.2f}（p={total[8]}）；I²={i2_text}"
    if tau is not None:
        het += f"；Tau²={tau:.3f}"
    lines.append(het)
    lines.append(f"总体效应：z={total[10]:.2f}，p={total[11]}")
    return "\n".join(lines)


def run_meta_analysis(
    records: list[EvidenceRecord],
    *,
    datatype: str,
    models: str,
    algorithm: str,
    effect: str,
    draw_plots: bool = True,
) -> MetaRunResult:
    """对纳入且提取完整的研究做合并；缺数据的研究跳过，不填 0。"""
    if datatype not in (DATATYPE_CATE, DATATYPE_CONT):
        raise ValueError("数据类型必须是二分类或连续。")
    if models not in MODEL_OPTIONS:
        raise ValueError("效应模型必须是 Fixed 或 Random。")
    if effect not in EFFECT_OPTIONS[datatype]:
        raise ValueError("效应量与数据类型不匹配。")
    allowed_alg = ALGORITHM_CATE if datatype == DATATYPE_CATE else ALGORITHM_CONT
    if algorithm not in allowed_alg:
        raise ValueError("算法与数据类型不匹配。")

    included = included_records(records)
    lines: list[str] = []
    skipped: list[str] = []
    for record in included:
        line = extraction_to_line(record, datatype)
        if line is None:
            skipped.append(record.pmid)
            continue
        lines.append(line)

    if len(lines) < 2:
        raise ValueError("至少需要 2 项提取完整的纳入研究才能做 meta 分析。")

    data = PMA.Data()
    meta = PMA.Meta()
    data.datatype = datatype
    studies = data.getdata(lines)
    meta.datatype = datatype
    meta.models = models
    meta.algorithm = algorithm
    meta.effect = effect
    results = meta.meta(studies)
    total = results[0]
    i2_raw = total[9]
    i2_value = float(i2_raw) if isinstance(i2_raw, (int, float)) else None
    tau_raw = total[12]
    tau_value = float(tau_raw) if isinstance(tau_raw, (int, float)) else None

    forest_fig = None
    funnel_fig = None
    if draw_plots:
        configure_matplotlib_cjk()
        fig = PMA.Fig()
        fig.title = f"{models} {algorithm} {effect}"
        forest_fig = fig.forest(results)
        funnel_fig = fig.funnel(results)

    eggers = None
    try:
        eggers = meta.Eggers_test(results)
    except Exception:
        eggers = None

    return MetaRunResult(
        n_studies=len(lines),
        skipped_pmids=skipped,
        pooled_effect=float(total[1]) if total[1] is not None else None,
        ci_low=float(total[3]) if total[3] is not None else None,
        ci_high=float(total[4]) if total[4] is not None else None,
        i2=i2_value,
        q=float(total[7]) if total[7] is not None else None,
        q_p=str(total[8]) if total[8] is not None else None,
        tau2=tau_value,
        z=float(total[10]) if total[10] is not None else None,
        z_p=str(total[11]) if total[11] is not None else None,
        text_table=_format_results_table(results),
        forest_fig=forest_fig,
        funnel_fig=funnel_fig,
        eggers=eggers,
        datatype=datatype,
        models=models,
        algorithm=algorithm,
        effect=effect,
    )


# PythonMeta 文档中的二分类示例，供回归测试
PYTHONMETA_SAMPLE_CATE = [
    "Fang 2015,15,40,24,37",
    "Gong 2012,10,40,18,35",
    "Liu 2015,30,50,40,50",
    "Long 2012,19,40,26,40",
    "Wang 2003,7,86,15,86",
]


def run_meta_from_lines(
    lines: list[str],
    *,
    datatype: str,
    models: str,
    algorithm: str,
    effect: str,
    draw_plots: bool = False,
) -> MetaRunResult:
    """直接用 PythonMeta 行格式计算（测试与示例用）。"""
    dummy = [
        EvidenceRecord(
            pmid=str(index),
            title=line.split(",")[0],
            extraction=_line_to_extraction(line, datatype),
            screening_status=ScreeningStatus.INCLUDE,
        )
        for index, line in enumerate(lines, start=1)
        if line.strip() and not line.strip().startswith("#")
    ]
    return run_meta_analysis(
        dummy,
        datatype=datatype,
        models=models,
        algorithm=algorithm,
        effect=effect,
        draw_plots=draw_plots,
    )


def _line_to_extraction(line: str, datatype: str) -> ExtractionData:
    parts = [item.strip() for item in line.split(",")]
    if datatype == DATATYPE_CATE:
        return ExtractionData(
            datatype=datatype,
            study_label=parts[0],
            e1=int(parts[1]),
            n1=int(parts[2]),
            e2=int(parts[3]),
            n2=int(parts[4]),
        )
    return ExtractionData(
        datatype=datatype,
        study_label=parts[0],
        m1=float(parts[1]),
        sd1=float(parts[2]),
        n1=int(float(parts[3])),
        m2=float(parts[4]),
        sd2=float(parts[5]),
        n2=int(float(parts[6])),
    )
