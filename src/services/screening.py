"""初筛业务逻辑。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from src.models.evidence import EXCLUSION_PRESETS, EvidenceRecord, ScreeningStatus

OTHER_PREFIX = "Other: "
EXCLUSION_PLACEHOLDER = "请选择排除原因"


@dataclass
class DedupeResult:
    """去重结果。"""

    records: list[EvidenceRecord]
    removed_count: int
    removed_pmids: list[str]


def dedupe_records(records: list[EvidenceRecord]) -> DedupeResult:
    """PMID 精确去重，其次 DOI 精确去重。"""
    seen_pmids: set[str] = set()
    seen_dois: set[str] = set()
    deduped: list[EvidenceRecord] = []
    removed_pmids: list[str] = []
    for record in records:
        if record.pmid in seen_pmids:
            removed_pmids.append(record.pmid)
            continue
        doi_key = record.doi.casefold() if record.doi else None
        if doi_key and doi_key in seen_dois:
            removed_pmids.append(record.pmid)
            continue
        seen_pmids.add(record.pmid)
        if doi_key:
            seen_dois.add(doi_key)
        deduped.append(record)
    return DedupeResult(
        records=deduped,
        removed_count=len(removed_pmids),
        removed_pmids=removed_pmids,
    )


def normalize_title(title: str) -> str:
    """标题标准化，用于相似度比较。"""
    normalized = title.lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def flag_potential_duplicates(
    records: list[EvidenceRecord],
    *,
    threshold: float = 0.92,
) -> list[EvidenceRecord]:
    """标题相似则标记 Potential Duplicate，不删除记录。"""
    flagged_pmids: set[str] = set()
    norms = [(record.pmid, normalize_title(record.title)) for record in records]
    for index, (pmid_a, norm_a) in enumerate(norms):
        if not norm_a:
            continue
        for pmid_b, norm_b in norms[index + 1 :]:
            if not norm_b:
                continue
            if norm_a == norm_b or SequenceMatcher(None, norm_a, norm_b).ratio() >= threshold:
                flagged_pmids.add(pmid_a)
                flagged_pmids.add(pmid_b)
    return [
        record.model_copy(update={"potential_duplicate": record.pmid in flagged_pmids})
        for record in records
    ]


def parse_exclusion_reason(reason: str | None) -> tuple[str, str]:
    """拆分为预设项与 Other 自定义说明。"""
    if not reason:
        return "", ""
    if reason.startswith(OTHER_PREFIX):
        return "Other", reason[len(OTHER_PREFIX) :]
    if reason in EXCLUSION_PRESETS:
        return reason, ""
    return "Other", reason


def format_exclusion_reason(preset: str, other_detail: str = "") -> str:
    """组合排除原因；Other 可附自定义说明。"""
    if preset != "Other":
        return preset
    detail = other_detail.strip()
    return f"{OTHER_PREFIX}{detail}" if detail else "Other"


def is_valid_exclusion_reason(reason: str) -> bool:
    """预设项，或 Other: 自定义说明。"""
    if reason in EXCLUSION_PRESETS:
        return True
    return reason.startswith(OTHER_PREFIX)


def count_by_status(records: list[EvidenceRecord]) -> dict[str, int]:
    """按初筛状态统计。"""
    counts = {
        "Total": len(records),
        "Unscreened": 0,
        "Include": 0,
        "Maybe": 0,
        "Exclude": 0,
    }
    for record in records:
        key = record.screening_status.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def filter_by_status(
    records: list[EvidenceRecord],
    status: ScreeningStatus | None,
) -> list[EvidenceRecord]:
    """按状态筛选；status 为 None 时返回全部。"""
    if status is None:
        return records
    return [r for r in records if r.screening_status == status]


def collect_publication_types(records: list[EvidenceRecord]) -> list[str]:
    """收集当前结果集中出现过的文献类型（去重、排序）。"""
    types: set[str] = set()
    for record in records:
        for pub_type in record.publication_types:
            if pub_type:
                types.add(pub_type)
    return sorted(types)


def filter_by_publication_types(
    records: list[EvidenceRecord],
    selected_types: list[str] | None,
) -> list[EvidenceRecord]:
    """按文献类型筛选；未选或空列表时返回全部。"""
    if not selected_types:
        return records
    selected = set(selected_types)
    return [r for r in records if selected.intersection(r.publication_types)]


def screening_progress(records: list[EvidenceRecord]) -> tuple[int, int]:
    """返回 (已初筛篇数, 总篇数)。"""
    total = len(records)
    unscreened = sum(1 for r in records if r.screening_status == ScreeningStatus.UNSCREENED)
    return total - unscreened, total


def bulk_update_records(
    records: list[EvidenceRecord],
    pmids: set[str],
    status: ScreeningStatus,
    exclusion_reason: str | None = None,
) -> list[EvidenceRecord]:
    """批量更新多篇文献的初筛状态。"""
    if not pmids:
        return records
    if status == ScreeningStatus.EXCLUDE:
        if not exclusion_reason or not is_valid_exclusion_reason(exclusion_reason):
            raise ValueError("批量排除须选择有效的排除原因。")

    updated: list[EvidenceRecord] = []
    for record in records:
        if record.pmid not in pmids:
            updated.append(record)
            continue
        if status == ScreeningStatus.EXCLUDE:
            stored_reason = exclusion_reason
        else:
            stored_reason = None
        updated.append(
            record.model_copy(
                update={
                    "screening_status": status,
                    "exclusion_reason": stored_reason,
                }
            )
        )
    return updated


def update_record(
    records: list[EvidenceRecord],
    pmid: str,
    status: ScreeningStatus,
    exclusion_reason: str | None = None,
    notes: str | None = None,
) -> list[EvidenceRecord]:
    """更新单篇文献的初筛字段，不修改 PubMed 元数据。"""
    if status == ScreeningStatus.EXCLUDE and exclusion_reason:
        if not is_valid_exclusion_reason(exclusion_reason):
            raise ValueError(f"排除原因必须是预设选项或 Other: 说明：{EXCLUSION_PRESETS}")

    updated: list[EvidenceRecord] = []
    for record in records:
        if record.pmid != pmid:
            updated.append(record)
            continue
        if status == ScreeningStatus.EXCLUDE:
            stored_reason = exclusion_reason
        else:
            stored_reason = None
        updated.append(
            record.model_copy(
                update={
                    "screening_status": status,
                    "exclusion_reason": stored_reason,
                    "notes": notes,
                }
            )
        )
    return updated
