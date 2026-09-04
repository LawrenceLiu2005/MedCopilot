"""第二位筛查者 CSV 导入与 Cohen's Kappa。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO

from src.models.evidence import EvidenceRecord, ScreeningStatus

STATUS_ALIASES: dict[str, ScreeningStatus] = {
    "unscreened": ScreeningStatus.UNSCREENED,
    "未筛": ScreeningStatus.UNSCREENED,
    "include": ScreeningStatus.INCLUDE,
    "纳入": ScreeningStatus.INCLUDE,
    "maybe": ScreeningStatus.MAYBE,
    "待定": ScreeningStatus.MAYBE,
    "exclude": ScreeningStatus.EXCLUDE,
    "排除": ScreeningStatus.EXCLUDE,
}

PMID_HEADERS = {"pmid", "id", "文献id"}
STATUS_HEADERS_R2 = {
    "reviewer 2 status",
    "reviewer2_status",
    "reviewer2",
    "筛查者2",
    "第二位",
    "第二位初筛",
}
STATUS_HEADERS_ANY = {
    "screening status",
    "status",
    "初筛",
    "状态",
    *STATUS_HEADERS_R2,
}


@dataclass
class Reviewer2ImportResult:
    """第二位筛查 CSV 导入摘要。"""

    applied: int
    skipped_unknown_pmid: list[str]
    skipped_invalid_status: list[str]
    skipped_empty: int


@dataclass
class KappaResult:
    """两人初筛一致性。"""

    n_compared: int
    n_agree: int
    n_disagree: int
    kappa: float | None
    labels: list[str]


def parse_screening_status(raw: str) -> ScreeningStatus | None:
    """解析初筛状态；无法识别则返回 None。"""
    text = (raw or "").strip()
    if not text:
        return None
    return STATUS_ALIASES.get(text.casefold()) or STATUS_ALIASES.get(text)


def _header_key(name: str) -> str:
    return name.strip().casefold()


def parse_reviewer2_csv(text: str) -> tuple[dict[str, ScreeningStatus], list[str]]:
    """解析 PMID + 初筛状态 CSV。优先读「Reviewer 2 Status」列。"""
    stripped = text.lstrip("\ufeff").strip()
    if not stripped:
        return {}, []
    reader = csv.DictReader(StringIO(stripped))
    if not reader.fieldnames:
        return {}, []
    headers = {_header_key(name): name for name in reader.fieldnames if name}
    pmid_col = next((headers[h] for h in headers if h in PMID_HEADERS), None)
    r2_col = next((headers[h] for h in headers if h in STATUS_HEADERS_R2), None)
    any_col = next((headers[h] for h in headers if h in STATUS_HEADERS_ANY), None)
    if pmid_col is None:
        return {}, []

    rows = list(reader)

    def _has_values(col: str | None) -> bool:
        if not col:
            return False
        return any(str(row.get(col) or "").strip() for row in rows)

    if r2_col and _has_values(r2_col):
        status_col = r2_col
    elif any_col and _has_values(any_col):
        status_col = any_col
    else:
        status_col = r2_col or any_col
    if status_col is None:
        return {}, []

    mapping: dict[str, ScreeningStatus] = {}
    invalid: list[str] = []
    for row in rows:
        pmid = str(row.get(pmid_col) or "").strip()
        raw_status = str(row.get(status_col) or "").strip()
        if not pmid:
            continue
        if not raw_status:
            continue
        status = parse_screening_status(raw_status)
        if status is None:
            invalid.append(pmid)
            continue
        mapping[pmid] = status
    return mapping, invalid


def apply_reviewer2_status(
    records: list[EvidenceRecord],
    mapping: dict[str, ScreeningStatus],
) -> tuple[list[EvidenceRecord], Reviewer2ImportResult]:
    """只写入 reviewer2_status，不改第一位筛查或 PubMed 字段。"""
    known = {record.pmid for record in records}
    skipped_unknown = sorted(pmid for pmid in mapping if pmid not in known)
    applied = 0
    updated: list[EvidenceRecord] = []
    for record in records:
        status = mapping.get(record.pmid)
        if status is None:
            updated.append(record)
            continue
        applied += 1
        updated.append(record.model_copy(update={"reviewer2_status": status}))
    result = Reviewer2ImportResult(
        applied=applied,
        skipped_unknown_pmid=skipped_unknown,
        skipped_invalid_status=[],
        skipped_empty=0,
    )
    return updated, result


def _decided(status: ScreeningStatus | None) -> bool:
    return status is not None and status != ScreeningStatus.UNSCREENED


def paired_decisions(
    records: list[EvidenceRecord],
) -> list[tuple[EvidenceRecord, ScreeningStatus, ScreeningStatus]]:
    """两人皆已做出纳入/待定/排除决策的记录。"""
    pairs: list[tuple[EvidenceRecord, ScreeningStatus, ScreeningStatus]] = []
    for record in records:
        if _decided(record.screening_status) and _decided(record.reviewer2_status):
            pairs.append((record, record.screening_status, record.reviewer2_status))
    return pairs


def disagreements(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    """两人决策不一致的文献。"""
    return [
        record
        for record, first, second in paired_decisions(records)
        if first != second
    ]


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    """Cohen's Kappa；样本为空返回 None。不引入 sklearn。"""
    if not labels_a or len(labels_a) != len(labels_b):
        return None
    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    categories = sorted(set(labels_a) | set(labels_b))
    expected = 0.0
    for category in categories:
        p_a = sum(1 for item in labels_a if item == category) / n
        p_b = sum(1 for item in labels_b if item == category) / n
        expected += p_a * p_b
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def compute_agreement(records: list[EvidenceRecord]) -> KappaResult:
    """计算两人已决策记录的一致率与 Kappa。"""
    pairs = paired_decisions(records)
    labels_a = [first.value for _, first, _ in pairs]
    labels_b = [second.value for _, _, second in pairs]
    n_agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    return KappaResult(
        n_compared=len(pairs),
        n_agree=n_agree,
        n_disagree=len(pairs) - n_agree,
        kappa=cohen_kappa(labels_a, labels_b),
        labels=labels_a,
    )


def kappa_caption(kappa: float | None) -> str:
    """Kappa 白话解释。"""
    if kappa is None:
        return "两人尚未对同一批文献都做出纳入/待定/排除决策，暂无法计算一致性。"
    if kappa < 0:
        return "一致性差（低于随机水平）"
    if kappa <= 0.20:
        return "一致性很弱"
    if kappa <= 0.40:
        return "一致性一般"
    if kappa <= 0.60:
        return "一致性中等"
    if kappa <= 0.80:
        return "一致性较好"
    return "一致性很好"


def reviewer2_template_csv(records: list[EvidenceRecord]) -> str:
    """给第二位筛查者填写的 CSV 模板。"""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["PMID", "Title", "Screening Status", "Reviewer 2 Status"])
    for record in records:
        writer.writerow(
            [
                record.pmid,
                record.title,
                record.screening_status.value,
                record.reviewer2_status.value if record.reviewer2_status else "",
            ]
        )
    return buffer.getvalue()
