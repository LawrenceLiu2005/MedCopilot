"""结果页 UI。"""

from __future__ import annotations

import math
from datetime import datetime

import streamlit as st

from src.models.evidence import EXCLUSION_PRESET_ZH, EXCLUSION_PRESETS, EvidenceRecord, ScreeningStatus
from src.services.export import filter_records_for_export, to_audit_report_md, to_csv, to_ris, to_search_snapshot
from src.services.screening import (
    EXCLUSION_PLACEHOLDER,
    bulk_update_records,
    collect_publication_types,
    count_by_status,
    filter_by_publication_types,
    filter_by_status,
    format_exclusion_reason,
    parse_exclusion_reason,
    screening_progress,
    update_record,
)
from src.services.search import SearchResult, attempted_retrieved_count

STATUS_OPTIONS = {
    "全部": None,
    "未筛": ScreeningStatus.UNSCREENED,
    "纳入": ScreeningStatus.INCLUDE,
    "待定": ScreeningStatus.MAYBE,
    "排除": ScreeningStatus.EXCLUDE,
}

SCREENING_CHOICES = [
    ScreeningStatus.UNSCREENED,
    ScreeningStatus.INCLUDE,
    ScreeningStatus.MAYBE,
    ScreeningStatus.EXCLUDE,
]

SCREENING_CHOICE_LABELS = {
    ScreeningStatus.UNSCREENED: "未筛",
    ScreeningStatus.INCLUDE: "纳入",
    ScreeningStatus.MAYBE: "待定",
    ScreeningStatus.EXCLUDE: "排除",
}

EXPORT_SCOPE_OPTIONS = {
    "全部": "all",
    "纳入 + 待定": "include_maybe",
    "仅纳入": "include",
    "当前筛选结果": "filtered",
}

RESULTS_PAGE_SIZE = 20

SORT_LABELS = {
    None: "相关度",
    "pub_date": "发表日期",
}


def render_results_page() -> None:
    """渲染结果页。"""
    st.header("结果")
    records: list[EvidenceRecord] = st.session_state.get("records", [])
    if not records:
        st.info("还没有文献。请到左侧「搜索」填写 PubMed 检索式并执行搜索。")
        return

    active = st.session_state.get("active_search")
    _render_search_context(active)
    _render_hit_banner(active, len(records))

    counts = count_by_status(records)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("合计", counts["Total"])
    c2.metric("未筛", counts["Unscreened"])
    c3.metric("纳入", counts["Include"])
    c4.metric("待定", counts["Maybe"])
    c5.metric("排除", counts["Exclude"])
    st.caption("纳入表示此阶段可能合格，不是系统评价的最终纳入。")

    screened, total = screening_progress(records)
    if total > 0:
        st.progress(screened / total, text=f"初筛进度：已筛 {screened} / {total} 篇")

    st.divider()
    if "results_status_filter" not in st.session_state:
        st.session_state.results_status_filter = "未筛"
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        filter_label = st.selectbox(
            "按状态筛选",
            options=list(STATUS_OPTIONS.keys()),
            key="results_status_filter",
        )
    with filter_col2:
        pub_types = collect_publication_types(records)
        selected_types = st.multiselect(
            "按文献类型筛选",
            options=pub_types,
            placeholder="全部类型",
        )

    filtered = filter_by_status(records, STATUS_OPTIONS[filter_label])
    filtered = filter_by_publication_types(filtered, selected_types or None)

    _render_bulk_actions(filtered)

    total_pages = max(1, math.ceil(len(filtered) / RESULTS_PAGE_SIZE))
    if "results_page" not in st.session_state:
        st.session_state.results_page = 0
    st.session_state.results_page = min(st.session_state.results_page, total_pages - 1)

    page = st.session_state.results_page
    start = page * RESULTS_PAGE_SIZE
    end = start + RESULTS_PAGE_SIZE
    page_records = filtered[start:end]

    if not filtered:
        st.info("当前筛选下没有文献，可改状态或文献类型筛选。")
    else:
        st.caption(
            f"显示第 {start + 1}–{min(end, len(filtered))} 篇，共 {len(filtered)} 篇"
            f"（第 {page + 1}/{total_pages} 页）"
        )
        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
        with nav_col1:
            if st.button("上一页", disabled=page <= 0):
                st.session_state.results_page = page - 1
                st.rerun()
        with nav_col3:
            if st.button("下一页", disabled=page >= total_pages - 1):
                st.session_state.results_page = page + 1
                st.rerun()

    for record in page_records:
        _render_card(record)

    sync_active_search()
    _render_export(st.session_state.records, filtered)


def _render_bulk_actions(filtered: list[EvidenceRecord]) -> None:
    """对当前筛选结果批量初筛。"""
    if not filtered:
        return
    with st.expander(f"批量初筛（当前筛选 {len(filtered)} 篇）", expanded=False):
        st.caption("仅作用于上方筛选后的文献；批量排除须先选原因。")
        bulk_col1, bulk_col2, bulk_col3, bulk_col4 = st.columns(4)
        pmids = {record.pmid for record in filtered}
        if bulk_col1.button("全部标为纳入", key="bulk_include"):
            st.session_state.records = bulk_update_records(
                st.session_state.records, pmids, ScreeningStatus.INCLUDE
            )
            st.rerun()
        if bulk_col2.button("全部标为待定", key="bulk_maybe"):
            st.session_state.records = bulk_update_records(
                st.session_state.records, pmids, ScreeningStatus.MAYBE
            )
            st.rerun()
        if bulk_col3.button("全部标为未筛", key="bulk_unscreened"):
            st.session_state.records = bulk_update_records(
                st.session_state.records, pmids, ScreeningStatus.UNSCREENED
            )
            st.rerun()
        with bulk_col4:
            bulk_reason = st.selectbox(
                "批量排除原因",
                options=[EXCLUSION_PLACEHOLDER, *EXCLUSION_PRESETS],
                format_func=_exclusion_label,
                key="bulk_exclude_reason",
            )
            if st.button("全部标为排除", key="bulk_exclude"):
                if bulk_reason == EXCLUSION_PLACEHOLDER:
                    st.error("批量排除前请选择原因。")
                else:
                    st.session_state.records = bulk_update_records(
                        st.session_state.records,
                        pmids,
                        ScreeningStatus.EXCLUDE,
                        exclusion_reason=bulk_reason,
                    )
                    st.rerun()


def _render_search_context(active: SearchResult | None) -> None:
    """结果页只读检索上下文，便于核对可复现性。"""
    if active is None:
        return
    year_from = active.year_from or "不限"
    year_to = active.year_to or "不限"
    executed = active.executed_at.strftime("%Y-%m-%d %H:%M UTC")
    if active.research_question:
        st.write(f"研究问题：{active.research_question}")
    st.markdown("**本次检索式**")
    st.code(active.query, language=None)
    st.caption(
        f"年份：{year_from} — {year_to} · 条数上限：{active.retmax} · "
        f"ID：{active.search_id} · 执行时间：{executed}"
    )


def _render_hit_banner(active, retrieved: int) -> None:
    """显示 PubMed 命中与拉回条数。"""
    if active is None:
        st.caption(f"已拉回 {retrieved} 篇")
        return

    sort_label = SORT_LABELS.get(getattr(active, "sort", None), "相关度")
    st.info(
        f"PubMed 命中 {active.total_hits} 篇 · 列表 {retrieved} 篇 · 排序：{sort_label}"
    )

    missing_pmids = getattr(active, "missing_pmids", None) or []
    if missing_pmids:
        st.warning(
            f"有 {len(missing_pmids)} 篇文献的元数据未能从 PubMed 拉回，结果列表可能不完整。"
        )
        with st.expander("查看未能拉回的 PMID"):
            st.code(", ".join(missing_pmids), language=None)

    dedupe_removed = getattr(active, "dedupe_removed_pmids", None) or []
    if dedupe_removed:
        st.caption(
            f"搜索时已去除 {len(dedupe_removed)} 篇重复（PMID/DOI 完全匹配）。"
        )

    attempted = attempted_retrieved_count(active, listed=retrieved)
    if active.total_hits > attempted:
        remaining = active.total_hits - attempted
        st.caption(
            f"还有 {remaining} 篇未拉回，可在搜索页提高返回条数或缩小年份范围。"
        )


def sync_active_search() -> None:
    """将初筛结果同步回当前检索与历史。"""
    active = st.session_state.get("active_search")
    if active is None:
        return
    active.records = [r.model_copy(deep=True) for r in st.session_state.records]
    for index, item in enumerate(st.session_state.history):
        if item.search_id == active.search_id:
            st.session_state.history[index] = active
            break


def _format_authors(authors: list[str]) -> str:
    if not authors:
        return "作者未知"
    if len(authors) == 1:
        return f"{authors[0]}"
    return f"{authors[0]} et al."


def _format_meta_line(record: EvidenceRecord) -> str:
    parts = [_format_authors(record.authors)]
    if record.publication_types:
        parts.append(record.publication_types[0])
    if record.journal:
        parts.append(record.journal)
    if record.publication_year:
        parts.append(str(record.publication_year))
    return " · ".join(parts)


def _render_abstract(text: str) -> None:
    """渲染摘要；结构化摘要按段落展示。"""
    sections = text.split("\n\n")
    if not any("\n" in section for section in sections):
        st.text(text)
        return

    for section in sections:
        if "\n" in section:
            label, _, body = section.partition("\n")
            if label and body:
                st.markdown(f"**{label}**")
                st.write(body)
                continue
        st.text(section)


def _exclusion_label(preset: str) -> str:
    if preset == EXCLUSION_PLACEHOLDER:
        return EXCLUSION_PLACEHOLDER
    zh = EXCLUSION_PRESET_ZH.get(preset)
    return f"{preset}（{zh}）" if zh else preset


def _export_filename(active: SearchResult | None, ext: str) -> str:
    if active is None:
        date = datetime.now().strftime("%Y%m%d")
        return f"evidence_nosid_{date}.{ext}"
    date = active.executed_at.strftime("%Y%m%d")
    return f"evidence_{active.search_id}_{date}.{ext}"


def _render_card(record: EvidenceRecord) -> None:
    """单篇文献卡片。"""
    with st.container(border=True):
        st.markdown(f"**{record.title}**")
        if record.potential_duplicate:
            st.caption("⚠ 可能重复（标题相似，请人工核对）")
        st.caption(_format_meta_line(record))

        id_parts = [
            f'<span class="mono-id">PMID <a href="https://pubmed.ncbi.nlm.nih.gov/{record.pmid}/">{record.pmid}</a></span>'
        ]
        if record.doi:
            id_parts.append(
                f'<span class="mono-id">DOI <a href="https://doi.org/{record.doi}">{record.doi}</a></span>'
            )
        st.markdown(" · ".join(id_parts), unsafe_allow_html=True)

        link_col1, link_col2 = st.columns(2)
        link_col1.link_button("打开 PubMed", f"https://pubmed.ncbi.nlm.nih.gov/{record.pmid}/")
        if record.doi:
            link_col2.link_button("打开 DOI", f"https://doi.org/{record.doi}")
        else:
            link_col2.caption("无 DOI")

        if record.abstract:
            with st.expander("摘要", expanded=True):
                _render_abstract(record.abstract)
        else:
            st.caption("摘要不可用")

        status_index = SCREENING_CHOICES.index(record.screening_status)
        new_status = st.radio(
            "初筛",
            options=SCREENING_CHOICES,
            index=status_index,
            format_func=lambda s: SCREENING_CHOICE_LABELS[s],
            horizontal=True,
            key=f"status_{record.pmid}",
        )

        exclusion_reason = record.exclusion_reason
        notes = record.notes or ""
        effective_status = new_status
        if new_status == ScreeningStatus.EXCLUDE:
            preset, other_detail = parse_exclusion_reason(exclusion_reason)
            reason_options = [EXCLUSION_PLACEHOLDER, *EXCLUSION_PRESETS]
            if preset in EXCLUSION_PRESETS:
                preset_index = reason_options.index(preset)
            else:
                preset_index = 0
            selected_preset = st.selectbox(
                "排除原因",
                options=reason_options,
                index=preset_index,
                format_func=_exclusion_label,
                key=f"reason_{record.pmid}",
            )
            if selected_preset == EXCLUSION_PLACEHOLDER:
                st.error("排除尚未记录：请选择原因（选好后才会写入排除）。")
                effective_status = record.screening_status
                exclusion_reason = record.exclusion_reason
            else:
                other_text = ""
                if selected_preset == "Other":
                    other_text = st.text_input(
                        "其他说明",
                        value=other_detail,
                        placeholder="请简要说明排除原因",
                        key=f"reason_other_{record.pmid}",
                    )
                exclusion_reason = format_exclusion_reason(selected_preset, other_text)
                if selected_preset == "Other" and exclusion_reason == "Other":
                    st.error("排除尚未记录：选择「其他」时请填写说明。")
                    effective_status = record.screening_status
                    exclusion_reason = record.exclusion_reason
        notes = st.text_input("笔记", value=notes, key=f"notes_{record.pmid}")

        reason_to_store = exclusion_reason if effective_status == ScreeningStatus.EXCLUDE else None
        st.session_state.records = update_record(
            st.session_state.records,
            record.pmid,
            effective_status,
            reason_to_store,
            notes or None,
        )


def _render_export(records: list[EvidenceRecord], filtered: list[EvidenceRecord]) -> None:
    """导出按钮。"""
    st.divider()
    st.header("导出")
    st.caption("默认导出全部文献（含初筛状态），便于完整留痕；导入文献软件时可改选「纳入 + 待定」。")
    scope_label = st.selectbox(
        "导出范围",
        options=list(EXPORT_SCOPE_OPTIONS.keys()),
        key="export_scope",
    )
    scope = EXPORT_SCOPE_OPTIONS[scope_label]
    export_records = filter_records_for_export(records, scope, filtered)
    st.caption(f"本次将导出 {len(export_records)} 篇。")

    active = st.session_state.get("active_search")
    ris_name = _export_filename(active, "ris")
    csv_name = _export_filename(active, "csv")
    if active is None:
        col1, col2 = st.columns(2)
        col1.download_button(
            "下载 RIS",
            to_ris(export_records),
            file_name=ris_name,
            mime="application/x-research-info-systems",
        )
        col2.download_button(
            "下载 CSV",
            to_csv(export_records),
            file_name=csv_name,
            mime="text/csv",
        )
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.download_button(
        "下载 RIS",
        to_ris(export_records),
        file_name=ris_name,
        mime="application/x-research-info-systems",
    )
    col2.download_button(
        "下载 CSV",
        to_csv(export_records),
        file_name=csv_name,
        mime="text/csv",
    )
    col3.download_button(
        "下载检索快照",
        to_search_snapshot(active, records=records),
        file_name=f"search_{active.search_id}.json",
        mime="application/json",
    )
    col4.download_button(
        "下载审计报告",
        to_audit_report_md(active, records=records),
        file_name=f"audit_{active.search_id}.md",
        mime="text/markdown",
        help="人类可读的检索记录，可贴进综述附录或用 Word/浏览器打印为 PDF",
    )
