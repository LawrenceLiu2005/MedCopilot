"""PRISMA 2020 流程图（整合 prisma-flow）。"""

from __future__ import annotations

from collections import Counter

from prismaflow import new_review

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.search import SearchResult


def _exclusion_breakdown(records: list[EvidenceRecord]) -> dict[str, int]:
    """按排除原因分组统计。"""
    counter: Counter[str] = Counter()
    for record in records:
        if record.screening_status != ScreeningStatus.EXCLUDE:
            continue
        reason = record.exclusion_reason or "未填写"
        if reason.startswith("Other:"):
            reason = "Other"
        counter[reason] += 1
    return dict(counter)


def build_prisma_flow(search: SearchResult, records: list[EvidenceRecord] | None = None):
    """从检索与初筛统计构建 PrismaFlow 对象。"""
    listed = records if records is not None else search.records
    counts = {
        status.value: sum(1 for r in listed if r.screening_status == status)
        for status in ScreeningStatus
    }
    dedupe_removed = len(search.dedupe_removed_pmids or [])
    records_identified = search.total_hits if search.total_hits else len(listed) + dedupe_removed
    records_after_dedupe = len(listed)
    records_excluded = counts.get("Exclude", 0)
    records_screened = records_after_dedupe
    reports_sought = counts.get("Include", 0) + counts.get("Maybe", 0)
    studies_included = counts.get("Include", 0)

    return new_review(
        records_identified_databases=records_identified,
        records_identified_registers=0,
        records_removed_duplicates=dedupe_removed,
        records_removed_automation=0,
        records_removed_other=0,
        records_screened=records_screened,
        records_excluded=records_excluded,
        reports_sought=reports_sought,
        reports_not_retrieved=0,
        reports_assessed=reports_sought,
        reports_excluded=_exclusion_breakdown(listed) or None,
        studies_included=studies_included,
        title=f"Evidence Copilot · {search.search_id}",
    )


def prisma_to_svg(search: SearchResult, records: list[EvidenceRecord] | None = None) -> str:
    """生成 PRISMA 流程图 SVG 文本。"""
    flow = build_prisma_flow(search, records)
    return flow.to_svg()


def prisma_to_png(search: SearchResult, records: list[EvidenceRecord] | None = None) -> bytes:
    """生成 PRISMA 流程图 PNG 字节。"""
    flow = build_prisma_flow(search, records)
    return flow.to_png()
