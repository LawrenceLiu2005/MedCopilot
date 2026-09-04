"""导出 RIS / CSV / Search Snapshot。"""

from __future__ import annotations

import json
from io import StringIO

import pandas as pd

from src.models.evidence import EvidenceRecord, ScreeningStatus
from src.services.dual_screening import compute_agreement, disagreements
from src.services.extraction_suggest import extraction_ai_entries
from src.services.screening import count_by_status, count_exclusion_reasons
from src.services.search import SearchResult, attempted_retrieved_count


def _pico_ai_json(payload: dict) -> str:
    """把 AI 审计字段写成 JSON 文本。"""
    return json.dumps(payload, ensure_ascii=False, indent=2)


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
                "Reviewer 2 Status": (
                    record.reviewer2_status.value if record.reviewer2_status else ""
                ),
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
        "pico_population": search.pico_population,
        "pico_intervention": search.pico_intervention,
        "pico_comparator": search.pico_comparator,
        "pico_outcome": search.pico_outcome,
        "inclusion_criteria": search.inclusion_criteria,
        "exclusion_criteria": search.exclusion_criteria,
        "source_type": search.source_type,
        "parent_search_id": search.parent_search_id,
        "translated_wos": search.translated_wos,
        "translated_ebsco": search.translated_ebsco,
        "suggested_query": search.suggested_query,
        "query_suggestion_blocks": search.query_suggestion_blocks,
        "study_types": search.study_types or [],
        "ctgov_query": search.ctgov_query,
        "ctgov_hits": search.ctgov_hits or [],
        "pico_ai_used": search.pico_ai_used,
        "pico_ai_model": search.pico_ai_model,
        "pico_ai_prompt_version": search.pico_ai_prompt_version,
        "pico_ai_source_text": search.pico_ai_source_text,
        "pico_ai_draft": search.pico_ai_draft,
        "pico_ai_accepted": search.pico_ai_accepted,
        "extraction_ai": extraction_ai_entries(listed),
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
        "reviewer2_summary": {
            status.value: sum(
                1 for r in listed if r.reviewer2_status == status
            )
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
        f"- **数据来源**：{search.source_type}",
        "",
    ]

    if search.parent_search_id:
        lines.append(f"- **Living Search 来源检索 ID**：{search.parent_search_id}")
        lines.append("")

    if search.research_question:
        lines.extend([
            "## 研究问题",
            "",
            search.research_question,
            "",
        ])

    pico_fields = [
        ("P（人群）", search.pico_population),
        ("I（干预）", search.pico_intervention),
        ("C（对照）", search.pico_comparator),
        ("O（结局）", search.pico_outcome),
    ]
    if any(value.strip() for _, value in pico_fields):
        lines.extend(["## PICO / 纳入排除标准", ""])
        for label, value in pico_fields:
            if value.strip():
                lines.append(f"- **{label}**：{value.strip()}")
        if search.inclusion_criteria.strip():
            lines.extend(["", "**纳入标准**", "", search.inclusion_criteria.strip(), ""])
        if search.exclusion_criteria.strip():
            lines.extend(["**排除标准**", "", search.exclusion_criteria.strip(), ""])
        lines.append("")

    if search.pico_ai_used:
        lines.extend(["## 白话拆分（AI 建议，已经过人工确认）", ""])
        if search.pico_ai_model:
            lines.append(f"- **模型**：{search.pico_ai_model}")
        if search.pico_ai_prompt_version:
            lines.append(f"- **提示词版本**：{search.pico_ai_prompt_version}")
        if search.pico_ai_source_text:
            lines.extend(["", "**原句**", "", search.pico_ai_source_text, ""])
        if search.pico_ai_draft:
            lines.extend(["**模型草稿**", "", "```json", _pico_ai_json(search.pico_ai_draft), "```", ""])
        if search.pico_ai_accepted:
            lines.extend(["**确认后采用**", "", "```json", _pico_ai_json(search.pico_ai_accepted), "```", ""])
        lines.append("主题词仍由 NCBI MeSH 匹配，模型不编造官方主题词。")
        lines.append("")

    extraction_ai = extraction_ai_entries(listed)
    if extraction_ai:
        lines.extend(["## 提取草稿（AI 建议，已经过人工确认）", ""])
        models = sorted(
            {
                str(item.get("ai_model"))
                for item in extraction_ai
                if item.get("ai_model")
            }
        )
        versions = sorted(
            {
                str(item.get("ai_prompt_version"))
                for item in extraction_ai
                if item.get("ai_prompt_version")
            }
        )
        if models:
            lines.append(f"- **模型**：{'、'.join(models)}")
        if versions:
            lines.append(f"- **提示词版本**：{'、'.join(versions)}")
        lines.append(f"- **已确认篇数**：{len(extraction_ai)}")
        lines.append(f"- **PMID**：{', '.join(item['pmid'] for item in extraction_ai)}")
        lines.append("")
        lines.append("数字仍须人工核对；摘要没有的字段保持空，不算 0。未写入 API 密钥。")
        lines.append("")

    lines.extend([
        "## 检索式",
        "",
        "```",
        search.query,
        "```",
        "",
    ])

    if search.suggested_query:
        lines.extend([
            "### 建议检索式（生成后经人工确认/修改）",
            "",
            "```",
            search.suggested_query,
            "```",
            "",
        ])
        if search.suggested_query.strip() != search.query.strip():
            lines.append("实际发送的检索式与建议式不同，以上两者均予保留。")
            lines.append("")

    if search.raw_query:
        lines.extend([
            f"- **原始输入**：{search.raw_query}",
            f"- **作者字段包装**：{'是' if search.author_wrap_applied else '否'}",
            "",
        ])

    if search.translated_wos or search.translated_ebsco:
        lines.extend([
            "## 跨库翻译检索式（仅供复制，本工具仍只搜 PubMed）",
            "",
        ])
        if search.translated_wos:
            lines.extend(["**Web of Science**", "", "```", search.translated_wos, "```", ""])
        if search.translated_ebsco:
            lines.extend(["**EBSCOHost**", "", "```", search.translated_ebsco, "```", ""])
        lines.extend([
            "> 当前不支持自动翻译到 Embase。翻译结果不会用于本工具的 PubMed 检索。",
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
    ])

    agreement = compute_agreement(listed)
    if agreement.n_compared:
        lines.extend([
            "## 双人初筛一致性",
            "",
            f"- **两人皆已决策**：{agreement.n_compared} 篇",
            f"- **一致**：{agreement.n_agree} 篇",
            f"- **不一致**：{agreement.n_disagree} 篇",
            f"- **Cohen's Kappa**：{agreement.kappa:.3f}" if agreement.kappa is not None else "- **Cohen's Kappa**：无法计算",
            "",
        ])
        disagree_list = disagreements(listed)
        if disagree_list:
            lines.extend(["### 不一致 PMID", "", ", ".join(r.pmid for r in disagree_list), ""])

    exclusion_counts = count_exclusion_reasons(listed)
    if exclusion_counts:
        lines.extend([
            "## 排除原因统计",
            "",
            "| 排除原因 | 篇数 |",
            "| --- | ---: |",
        ])
        for reason, count in sorted(exclusion_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| {reason} | {count} |")
        lines.append("")

    lines.extend([
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


def to_methods_draft_md(
    search: SearchResult,
    records: list[EvidenceRecord] | None = None,
) -> str:
    """按 PRISMA-S 能自动填写的项生成检索方法草稿；无法推断的项标「需作者补全」。"""
    listed = records if records is not None else search.records
    executed = search.executed_at.strftime("%Y-%m-%d")
    year_from = str(search.year_from) if search.year_from is not None else "不限"
    year_to = str(search.year_to) if search.year_to is not None else "不限"
    counts = count_by_status(listed)
    attempted = attempted_retrieved_count(search, listed=len(listed))
    dedupe_n = len(search.dedupe_removed_pmids or [])
    source_label = "PubMed" if search.source_type == "pubmed_search" else search.source_type

    if search.year_from is not None or search.year_to is not None:
        year_clause = f"检索年限为 {year_from}–{year_to}。"
    else:
        year_clause = "未限制发表年份。"

    paragraph_parts = [
        f"于 {executed} 在 {source_label} 进行文献检索。",
        year_clause,
        f"检索式原文为：{search.query}。",
        f"数据库报告命中 {search.total_hits} 篇，本次工作台拉回 {len(listed)} 篇",
    ]
    if search.total_hits > attempted:
        paragraph_parts[-1] += f"（条数上限 {search.retmax}，尚未拉回全部命中）"
    paragraph_parts[-1] += "。"
    if dedupe_n:
        paragraph_parts.append(
            f"按 PMID 精确匹配、其次 DOI 精确匹配去除重复 {dedupe_n} 篇；标题相似仅标记为可能重复，不自动删除。"
        )
    else:
        paragraph_parts.append("去重规则为 PMID 精确匹配，其次 DOI 精确匹配；标题相似仅标记、不删除。")
    paragraph_parts.append(
        f"标题/摘要初筛结果：纳入 {counts['Include']} 篇，待定 {counts['Maybe']} 篇，"
        f"排除 {counts['Exclude']} 篇，未筛 {counts['Unscreened']} 篇。"
        "此处纳入表示本阶段可能合格，不是系统评价的最终纳入。"
    )
    if search.inclusion_criteria.strip() or search.exclusion_criteria.strip():
        if search.inclusion_criteria.strip():
            paragraph_parts.append(f"预先填写的纳入标准：{search.inclusion_criteria.strip()}。")
        if search.exclusion_criteria.strip():
            paragraph_parts.append(f"预先填写的排除标准：{search.exclusion_criteria.strip()}。")
    methods_paragraph = "".join(paragraph_parts)

    lines = [
        "# 检索方法草稿（PRISMA-S）",
        "",
        "> 本草稿由 Evidence Copilot 根据本次检索记录自动填写。"
        "标「需作者补全」的条目未在工具内记录，请勿假装已经检索。",
        "",
        "## 可粘贴的方法学段落",
        "",
        methods_paragraph,
        "",
        "## PRISMA-S 条目",
        "",
        f"1. **数据库名称**：{source_label}",
        "2. **是否检索多个数据库**：需作者补全（本工具本次只记录 PubMed）",
        (
            f"3. **研究注册库**：ClinicalTrials.gov，检索式见下"
            if search.ctgov_query
            else "3. **研究注册库**：需作者补全（如 ClinicalTrials.gov、WHO ICTRP）"
        ),
        "4. **网站、机构库等灰色文献**：需作者补全",
        "5. **引文检索 / 参考文献追索**：需作者补全",
        "6. **联系作者或专家**：需作者补全",
        "7. **其他检索途径**：需作者补全",
        "8. **检索策略（精确检索式）**：",
        "",
        "```",
        search.query,
        "```",
        "",
    ]

    if search.suggested_query:
        lines.extend([
            "建议检索式（生成后经人工核对）：",
            "",
            "```",
            search.suggested_query,
            "```",
            "",
        ])
    if search.ctgov_query:
        lines.extend([
            "ClinicalTrials.gov 对照检索式：",
            "",
            "```",
            search.ctgov_query,
            "```",
            "",
        ])

    lines.extend([
        f"9. **限制条件**：年份 {year_from}–{year_to}；返回条数上限 {search.retmax}；排序 {_sort_label(search.sort)}",
        "10. **检索过滤器（如 RCT 高度敏感策略）**：需作者补全（除非已写进上方检索式）",
        f"11. **检索日期**：{executed}",
        "12. **检索策略同行评议（PRESS）**：需作者补全",
        f"13. **覆盖时间范围**：{year_from}–{year_to}",
        f"14. **检索结果**：数据库命中 {search.total_hits} 篇；工作台拉回 {len(listed)} 篇",
        f"15. **去重**：PMID/DOI 精确匹配移除 {dedupe_n} 篇；标题相似仅标记",
        "16. **记录管理**：使用 Evidence Copilot 保存检索快照、初筛状态与审计报告",
        "",
    ])

    if search.translated_wos or search.translated_ebsco:
        lines.extend(["## 跨库翻译检索式（未在本工具执行）", ""])
        if search.translated_wos:
            lines.extend(["**Web of Science（仅供复制）**", "", "```", search.translated_wos, "```", ""])
        if search.translated_ebsco:
            lines.extend(["**EBSCOHost（仅供复制）**", "", "```", search.translated_ebsco, "```", ""])
        lines.extend(["当前不支持自动翻译到 Embase。", ""])

    pico_bits = [
        ("P（人群）", search.pico_population),
        ("I（干预）", search.pico_intervention),
        ("C（对照）", search.pico_comparator),
        ("O（结局）", search.pico_outcome),
    ]
    if any(value.strip() for _, value in pico_bits):
        lines.extend(["## 已填写的 PICO", ""])
        for label, value in pico_bits:
            if value.strip():
                lines.append(f"- **{label}**：{value.strip()}")
        lines.append("")

    if search.pico_ai_used:
        lines.extend(
            [
                "## 白话拆分说明",
                "",
                "研究问题曾由 DeepSeek 拆成英文 PICO，经人工确认后写入检索式；"
                "官方主题词仍来自 NCBI MeSH。",
                "",
            ]
        )

    if extraction_ai_entries(listed):
        lines.extend(
            [
                "## 提取说明",
                "",
                "部分纳入文献的事件数或均数曾由 DeepSeek 根据摘要或全文（PMC / 开放 PDF / 上传 PDF）提出草稿，"
                "经人工确认后写入提取表；空值不算 0。不绕过付费墙自动下载。",
                "",
            ]
        )

    lines.extend([
        "---",
        "",
        "*Evidence Copilot — 草稿仅供作者修订，不替代完整系统评价报告。*",
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
