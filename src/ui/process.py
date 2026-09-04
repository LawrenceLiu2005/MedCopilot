"""流程可视化：每一步怎么筛、怎么拼检索式。"""

from __future__ import annotations

import streamlit as st

from src.clients.clinicaltrials import (
    ClinicalTrialsClient,
    ClinicalTrialsError,
    build_ctgov_query,
    hit_from_dict,
)
from src.models.evidence import EXCLUSION_PRESET_ZH, EvidenceRecord, ScreeningStatus
from src.services.meta_analysis import extraction_is_complete, included_records
from src.services.prisma_diagram import prisma_to_png
from src.services.query_suggest import (
    QuerySuggestion,
    format_suggestion_blocks,
    suggestion_from_payload,
)
from src.services.screening import count_by_status, count_exclusion_reasons, screening_progress
from src.services.search import SearchResult, attempted_retrieved_count

SCREENING_CHOICE_LABELS = {
    ScreeningStatus.UNSCREENED: "未筛",
    ScreeningStatus.INCLUDE: "纳入",
    ScreeningStatus.MAYBE: "待定",
    ScreeningStatus.EXCLUDE: "排除",
}
SORT_LABELS = {
    None: "相关度",
    "pub_date": "发表日期",
}

PIPELINE_STEPS: list[tuple[str, str]] = [
    ("question", "研究问题"),
    ("query", "检索式"),
    ("search", "检索"),
    ("dedupe", "去重"),
    ("screen", "初筛"),
    ("extract", "提取"),
    ("meta", "Meta"),
]


def _sync_active() -> None:
    """把登记库对照结果写回当前检索与历史。"""
    active = st.session_state.get("active_search")
    if active is None:
        return
    active.records = [r.model_copy(deep=True) for r in st.session_state.get("records", [])]
    for index, item in enumerate(st.session_state.get("history", [])):
        if item.search_id == active.search_id:
            st.session_state.history[index] = active
            break


def _current_suggestion(active: SearchResult | None) -> QuerySuggestion | None:
    session_suggestion = st.session_state.get("query_suggestion")
    if isinstance(session_suggestion, QuerySuggestion):
        return session_suggestion
    if active is None:
        return None
    generated = active.executed_at if active.suggested_query else None
    return suggestion_from_payload(
        active.suggested_query,
        active.query_suggestion_blocks,
        active.study_types,
        generated,
    )


def render_pipeline_stepper(*, compact: bool = False) -> None:
    """步骤条：点哪步看哪步的事实。"""
    active: SearchResult | None = st.session_state.get("active_search")
    records: list[EvidenceRecord] = st.session_state.get("records") or []
    suggestion = _current_suggestion(active)
    statuses = _step_statuses(active, records, suggestion)
    labels = [f"{label}（{statuses[key]}）" for key, label in PIPELINE_STEPS]
    if compact:
        st.caption("流程：" + " → ".join(label for _, label in PIPELINE_STEPS))
        return
    st.markdown("**当前做到哪一步**")
    st.caption(" · ".join(labels))


def _step_statuses(
    active: SearchResult | None,
    records: list[EvidenceRecord],
    suggestion: QuerySuggestion | None,
) -> dict[str, str]:
    has_question = bool(
        (active and active.research_question.strip())
        or st.session_state.get("search_research_question")
    )
    has_query = bool(active and active.query.strip()) or bool(
        st.session_state.get("search_query")
    )
    has_search = active is not None
    dedupe_n = len(active.dedupe_removed_pmids or []) if active else 0
    screened, total = screening_progress(records) if records else (0, 0)
    included = included_records(records)
    extracted = sum(
        1
        for record in included
        if extraction_is_complete(record.extraction, _extraction_datatype())
    )
    return {
        "question": "已填" if has_question else "未填",
        "query": "已有建议" if suggestion and suggestion.suggested_query else ("已填" if has_query else "未填"),
        "search": f"命中 {active.total_hits}" if has_search else "未检索",
        "dedupe": f"移除 {dedupe_n}" if has_search else "—",
        "screen": f"{screened}/{total}" if total else "—",
        "extract": f"{extracted}/{len(included)}" if included else "—",
        "meta": "可计算" if extracted >= 2 else "不足 2 项",
    }


def _extraction_datatype() -> str:
    label = st.session_state.get("meta_datatype_label") or "二分类"
    return "CONT" if label == "连续" else "CATE"


def render_process_page() -> None:
    """渲染流程页。"""
    st.header("流程")
    st.caption(
        "这里只展示已经发生的步骤：怎么拼检索式、怎么去重、怎么初筛。"
        "不会自动改检索式。提取数字可从摘要生成草稿，须核对后才写入；空格子不算 0。"
    )
    render_pipeline_stepper()
    active: SearchResult | None = st.session_state.get("active_search")
    records: list[EvidenceRecord] = st.session_state.get("records") or []
    suggestion = _current_suggestion(active)

    step_labels = [label for _, label in PIPELINE_STEPS]
    step_keys = [key for key, _ in PIPELINE_STEPS]
    selected = st.radio("查看步骤", options=step_labels, horizontal=True, key="process_step")
    key = step_keys[step_labels.index(selected)]

    if key == "question":
        _render_question_step(active)
    elif key == "query":
        _render_query_step(active, suggestion)
    elif key == "search":
        _render_search_step(active, records)
    elif key == "dedupe":
        _render_dedupe_step(active)
    elif key == "screen":
        _render_screen_step(records)
    elif key == "extract":
        _render_extract_step(records)
    else:
        _render_meta_step(records)

    st.divider()
    _render_ctgov_section(active)
    if active is not None:
        st.divider()
        st.subheader("PRISMA 流程图")
        try:
            st.image(prisma_to_png(active, records=records))
        except Exception as exc:
            st.warning(f"流程图未能生成：{exc}")


def _render_question_step(active: SearchResult | None) -> None:
    question = (active.research_question if active else "") or st.session_state.get(
        "search_research_question", ""
    )
    if question and str(question).strip():
        st.write(str(question).strip())
    else:
        st.info("还没有填写研究问题。请到「搜索」页填写；中文白话可在搜索页用 AI 拆成 PICO。")
    pico = [
        ("P（人群）", (active.pico_population if active else "") or st.session_state.get("search_pico_population", "")),
        ("I（干预）", (active.pico_intervention if active else "") or st.session_state.get("search_pico_intervention", "")),
        ("C（对照）", (active.pico_comparator if active else "") or st.session_state.get("search_pico_comparator", "")),
        ("O（结局）", (active.pico_outcome if active else "") or st.session_state.get("search_pico_outcome", "")),
    ]
    filled = [(label, value) for label, value in pico if str(value).strip()]
    if filled:
        for label, value in filled:
            st.write(f"**{label}**：{value}")
    else:
        st.caption("PICO 尚未填写。")
    if active and active.pico_ai_used:
        st.caption(
            "本条检索的 PICO 曾由 AI 从白话拆出，并经过人工确认。"
            + (f" 模型：{active.pico_ai_model}。" if active.pico_ai_model else "")
        )
        if active.pico_ai_source_text:
            st.caption(f"原句：{active.pico_ai_source_text}")
    elif (st.session_state.get("pico_ai_audit") or {}).get("used"):
        st.caption("当前会话已确认过 AI 拆出的 PICO；检索后会写入快照。")


def _render_query_step(active: SearchResult | None, suggestion: QuerySuggestion | None) -> None:
    if suggestion and suggestion.suggested_query:
        st.markdown("**建议检索式**")
        st.code(suggestion.suggested_query, language=None)
        st.markdown(format_suggestion_blocks(suggestion))
    else:
        st.info("还没有生成建议。请到「搜索」页根据 PICO 生成，并点「采用建议」后才会写入检索框。")
    actual = active.query if active else st.session_state.get("search_query", "")
    if actual and str(actual).strip():
        st.markdown("**实际将发送 / 已发送的检索式**")
        st.code(str(actual).strip(), language=None)
        if suggestion and suggestion.suggested_query.strip() != str(actual).strip():
            st.warning("实际检索式与建议式不同。这是允许的：人以最终框里的式子为准。")


def _render_search_step(active: SearchResult | None, records: list[EvidenceRecord]) -> None:
    if active is None:
        st.info("还没有执行检索。")
        return
    sort_label = SORT_LABELS.get(getattr(active, "sort", None), "相关度")
    st.write(f"执行时间：{active.executed_at.strftime('%Y-%m-%d %H:%M UTC')}")
    st.write(f"PubMed 命中：{active.total_hits} 篇 · 列表：{len(records)} 篇 · 排序：{sort_label}")
    attempted = attempted_retrieved_count(active, listed=len(records))
    if active.total_hits > attempted:
        st.caption(f"还有 {active.total_hits - attempted} 篇未拉回（受返回条数上限限制）。")
    if active.missing_pmids:
        st.warning(f"有 {len(active.missing_pmids)} 篇元数据未能拉回。")
        st.code(", ".join(active.missing_pmids), language=None)


def _render_dedupe_step(active: SearchResult | None) -> None:
    if active is None:
        st.info("还没有检索，无从去重。")
        return
    removed = active.dedupe_removed_pmids or []
    st.write(f"PMID/DOI 完全匹配移除：{len(removed)} 篇。标题相似只标记、不删除。")
    if removed:
        st.code(", ".join(removed), language=None)
    else:
        st.caption("本次没有因 PMID/DOI 完全匹配而移除的记录。")


def _render_screen_step(records: list[EvidenceRecord]) -> None:
    if not records:
        st.info("还没有文献可初筛。")
        return
    counts = count_by_status(records)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("合计", counts["Total"])
    c2.metric("未筛", counts["Unscreened"])
    c3.metric("纳入", counts["Include"])
    c4.metric("待定", counts["Maybe"])
    c5.metric("排除", counts["Exclude"])
    exclusion_counts = count_exclusion_reasons(records)
    if exclusion_counts:
        st.subheader("排除原因")
        st.bar_chart(exclusion_counts)
    st.subheader("初筛改判历史")
    history_rows = []
    for record in records:
        if not record.screening_history:
            continue
        for entry in record.screening_history:
            reason = entry.exclusion_reason or ""
            if reason in EXCLUSION_PRESET_ZH:
                reason = EXCLUSION_PRESET_ZH[reason]
            history_rows.append(
                {
                    "PMID": record.pmid,
                    "时间": entry.changed_at.strftime("%Y-%m-%d %H:%M"),
                    "状态": SCREENING_CHOICE_LABELS.get(entry.status, entry.status.value),
                    "排除原因": reason,
                }
            )
    if history_rows:
        st.dataframe(history_rows, hide_index=True, use_container_width=True)
    else:
        st.caption("还没有改判记录。在「结果」页点纳入/排除后会出现在这里。")


def _render_extract_step(records: list[EvidenceRecord]) -> None:
    included = included_records(records)
    if not included:
        st.info("还没有纳入的文献。请先在「结果」页标记纳入，再到「Meta 分析」填提取表。")
        return
    datatype = _extraction_datatype()
    complete = [
        record for record in included if extraction_is_complete(record.extraction, datatype)
    ]
    st.write(f"纳入 {len(included)} 篇，其中提取完整 {len(complete)} 篇。")
    st.caption(
        "可到「Meta 分析」从摘要生成数字草稿，核对确认后才写入；"
        "空着的研究不会被当成 0，也不会自动开始合并。"
    )
    rows = []
    for record in included:
        ext = record.extraction
        rows.append(
            {
                "PMID": record.pmid,
                "标题": record.title[:80],
                "完整": "是" if extraction_is_complete(ext, datatype) else "否",
                "摘要草稿": "已确认" if ext is not None and ext.ai_used else "否",
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_meta_step(records: list[EvidenceRecord]) -> None:
    included = included_records(records)
    datatype = _extraction_datatype()
    complete_n = sum(
        1 for record in included if extraction_is_complete(record.extraction, datatype)
    )
    if complete_n >= 2:
        st.success(f"已有 {complete_n} 项提取完整，可到「Meta 分析」出图。")
    else:
        st.info("至少需要 2 项提取完整的纳入研究才能合并。请到「Meta 分析」核对摘要草稿或手填。")


def _render_ctgov_section(active: SearchResult | None) -> None:
    st.subheader("ClinicalTrials.gov 对照（登记库，不是文献）")
    st.caption(
        "用同一套 PICO 关键词去查试验登记，结果单独列出，不会和 PubMed 文献混在一起。"
    )
    pico_population = (active.pico_population if active else "") or st.session_state.get(
        "search_pico_population", ""
    )
    pico_intervention = (active.pico_intervention if active else "") or st.session_state.get(
        "search_pico_intervention", ""
    )
    pico_comparator = (active.pico_comparator if active else "") or st.session_state.get(
        "search_pico_comparator", ""
    )
    pico_outcome = (active.pico_outcome if active else "") or st.session_state.get(
        "search_pico_outcome", ""
    )
    research_question = (active.research_question if active else "") or st.session_state.get(
        "search_research_question", ""
    )
    preview = build_ctgov_query(
        population=str(pico_population),
        intervention=str(pico_intervention),
        comparator=str(pico_comparator),
        outcome=str(pico_outcome),
        research_question=str(research_question),
    )
    if preview:
        st.markdown("**将发送给 ClinicalTrials.gov**")
        st.code(preview, language=None)
    else:
        st.info("请先填写 PICO 或研究问题。")

    if st.button("检索 ClinicalTrials.gov", key="btn_ctgov_search"):
        if not preview.strip():
            st.warning("没有可用的对照检索词。")
        else:
            try:
                with st.spinner("正在查询 ClinicalTrials.gov…"):
                    total, hits = ClinicalTrialsClient().search(preview)
            except ClinicalTrialsError as exc:
                st.error(str(exc))
            else:
                payload = [hit.to_dict() for hit in hits]
                st.session_state.ctgov_query = preview
                st.session_state.ctgov_hits = payload
                st.session_state.ctgov_total = total
                if active is not None:
                    active.ctgov_query = preview
                    active.ctgov_hits = payload
                    _sync_active()
                st.success(
                    f"登记库命中 {total if total is not None else '未知'} 条，本页显示 {len(hits)} 条。"
                )
                st.rerun()

    stored_query = (active.ctgov_query if active else None) or st.session_state.get("ctgov_query")
    stored_hits = (active.ctgov_hits if active else None) or st.session_state.get("ctgov_hits") or []
    if stored_query:
        st.caption(f"上次对照检索式：{stored_query}")
    hits = [hit_from_dict(item) for item in stored_hits if isinstance(item, dict)]
    if not hits:
        return
    for hit in hits:
        with st.container(border=True):
            st.markdown(f"**{hit.title}**")
            status = hit.status or "状态未知"
            st.caption(f"{hit.nct_id} · {status}")
            st.link_button("打开登记页", hit.url)
