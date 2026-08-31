"""导出 RIS / CSV / Search Snapshot。"""

from __future__ import annotations

import json
from io import StringIO

import pandas as pd

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.search import SearchResult


def _author_line(author: str) -> str:
    parts = author.rsplit(" ", 1)
    if len(parts) == 2:
        return f"AU  - {parts[1]}, {parts[0]}"
    return f"AU  - {author}"


def to_ris(records: list[EvidenceRecord]) -> str:
    """导出 RIS 格式。"""
    lines: list[str] = []
    for record in records:
        lines.append("TY  - JOUR")
        for author in record.authors:
            lines.append(_author_line(author))
        lines.append(f"TI  - {record.title}")
        if record.journal:
            lines.append(f"JO  - {record.journal}")
        if record.publication_year:
            lines.append(f"PY  - {record.publication_year}")
        if record.doi:
            lines.append(f"DO  - {record.doi}")
        if record.abstract:
            lines.append(f"AB  - {record.abstract}")
        lines.append(f"AN  - {record.pmid}")
        lines.append(f"UR  - https://pubmed.ncbi.nlm.nih.gov/{record.pmid}/")
        lines.append("ER  - ")
    return "\n".join(lines) + ("\n" if lines else "")


def to_csv(records: list[EvidenceRecord]) -> str:
    """导出 CSV 格式。"""
    rows = []
    for record in records:
        rows.append(
            {
                "PMID": record.pmid,
                "DOI": record.doi or "",
                "Title": record.title,
                "Authors": "; ".join(record.authors),
                "Journal": record.journal or "",
                "Year": record.publication_year or "",
                "Publication Type": "; ".join(record.publication_types),
                "Abstract": record.abstract or "",
                "Screening Status": record.screening_status.value,
                "Exclusion Reason": record.exclusion_reason or "",
                "Notes": record.notes or "",
                "Potential Duplicate": "Yes" if record.potential_duplicate else "",
                "PubMed URL": f"https://pubmed.ncbi.nlm.nih.gov/{record.pmid}/",
                "DOI URL": f"https://doi.org/{record.doi}" if record.doi else "",
            }
        )
    df = pd.DataFrame(rows)
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue()


def to_search_snapshot(
    search: SearchResult,
    records: list[EvidenceRecord] | None = None,
) -> str:
    """导出检索快照 JSON。"""
    listed = records if records is not None else search.records
    payload = {
        "search_id": search.search_id,
        "search_date": search.executed_at.isoformat(),
        "research_question": search.research_question,
        "exact_query": search.query,
        "raw_query": search.raw_query,
        "author_wrap_applied": search.author_wrap_applied,
        "year_from": search.year_from,
        "year_to": search.year_to,
        "retmax": search.retmax,
        "sort": search.sort,
        "total_hits": search.total_hits,
        "retrieved_count": len(listed),
        "retrieved_pmids": [r.pmid for r in listed],
        "missing_pmids": search.missing_pmids or [],
        "dedupe_removed_pmids": search.dedupe_removed_pmids or [],
        "screening_summary": {
            status.value: sum(1 for r in listed if r.screening_status == status)
            for status in ScreeningStatus
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sort_label(sort: str | None) -> str:
    if sort == "pub_date":
        return "发表日期"
    return "相关度"


def to_audit_report_md(
    search: SearchResult,
    records: list[EvidenceRecord] | None = None,
) -> str:
    """导出人类可读的检索审计报告（Markdown，可贴进综述附录或打印为 PDF）。"""
    listed = records if records is not None else search.records
    executed = search.executed_at.strftime("%Y-%m-%d %H:%M UTC")
    year_from = search.year_from if search.year_from is not None else "不限"
    year_to = search.year_to if search.year_to is not None else "不限"
    missing = search.missing_pmids or []
    dedupe_removed = search.dedupe_removed_pmids or []

    screening_lines = []
    for status in ScreeningStatus:
        count = sum(1 for r in listed if r.screening_status == status)
        screening_lines.append(f"| {status.value} | {count} |")

    lines = [
        "# Evidence Copilot 检索审计报告",
        "",
        "> 本报告由 Evidence Copilot 自动生成，记录 PubMed 检索与初筛摘要，"
        "可直接作为综述方法学附录的检索记录草稿。",
        "",
        "## 基本信息",
        "",
        f"- **检索 ID**：{search.search_id}",
        f"- **执行时间**：{executed}",
        f"- **数据来源**：PubMed（NCBI E-utilities）",
        "",
    ]

    if search.research_question:
        lines.extend([
            "## 研究问题",
            "",
            search.research_question,
            "",
        ])

    lines.extend([
        "## 检索式",
        "",
        "```",
        search.query,
        "```",
        "",
    ])

    if search.raw_query:
        lines.extend([
            f"- **原始输入**：{search.raw_query}",
            f"- **作者字段包装**：{'是' if search.author_wrap_applied else '否'}",
            "",
        ])

    lines.extend([
        "## 检索参数",
        "",
        f"- **年份范围**：{year_from} — {year_to}",
        f"- **返回条数上限**：{search.retmax}",
        f"- **排序**：{_sort_label(search.sort)}",
        "",
        "## 命中与拉回",
        "",
        f"- **PubMed 总命中**：{search.total_hits} 篇",
        f"- **本次拉回（去重后列表）**：{len(listed)} 篇",
        f"- **元数据未能拉回**：{len(missing)} 篇",
        f"- **搜索时去重移除（PMID/DOI 完全匹配）**：{len(dedupe_removed)} 篇",
        "",
    ])

    if missing:
        lines.extend([
            "### 未能拉回的 PMID",
            "",
            ", ".join(missing),
            "",
        ])

    if dedupe_removed:
        lines.extend([
            "### 去重移除的 PMID",
            "",
            ", ".join(dedupe_removed),
            "",
        ])

    lines.extend([
        "## 初筛统计",
        "",
        "| 状态 | 篇数 |",
        "| --- | ---: |",
        *screening_lines,
        "",
        "## 已拉回 PMID",
        "",
        ", ".join(record.pmid for record in listed) if listed else "（无）",
        "",
        "---",
        "",
        "*Evidence Copilot — Reliable · Reproducible · Researcher-controlled*",
        "",
    ])
    return "\n".join(lines)


def filter_records_for_export(
    records: list[EvidenceRecord],
    scope: str,
    filtered: list[EvidenceRecord] | None = None,
) -> list[EvidenceRecord]:
    """按范围挑选导出文献。scope: all / include_maybe / include / filtered。"""
    if scope == "include_maybe":
        return [
            r
            for r in records
            if r.screening_status in (ScreeningStatus.INCLUDE, ScreeningStatus.MAYBE)
        ]
    if scope == "include":
        return [r for r in records if r.screening_status == ScreeningStatus.INCLUDE]
    if scope == "filtered":
        return list(filtered or [])
    return list(records)
