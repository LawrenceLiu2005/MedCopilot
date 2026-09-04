"""历史页 UI。"""

from __future__ import annotations

import streamlit as st

from src.clients.pubmed import PubMedConfigError, PubMedError
from src.services.screening import count_by_status
from src.services.search import SearchParams, SearchResult, compare_search_pmids, merge_living_search, run_search
from src.services.query_translate import translate_pubmed_query, translation_text
from src.services.storage import save_workspace, workspace_from_json, workspace_to_json
from src.ui.results import SORT_LABELS, sync_active_search
from src.ui.search import _activate_search_result, _finalize_records, apply_search_to_form
from src.ui.setup import build_pubmed_client


def render_history_page() -> None:
    """渲染历史页。"""
    st.header("历史")
    st.caption("自动保存到本地；也可导出备份、导入恢复。")
    history: list[SearchResult] = st.session_state.get("history", [])
    if not history:
        st.info("还没有历史。完成一次搜索后，记录会出现在这里，可重新打开。")
    else:
        for index, item in enumerate(reversed(history)):
            with st.container(border=True):
                ts = item.executed_at.strftime("%Y-%m-%d %H:%M")
                st.markdown(
                    f'<span class="mono-id">{ts}</span> · '
                    f'<span class="mono-id">ID {item.search_id}</span>',
                    unsafe_allow_html=True,
                )
                if item.research_question:
                    st.write(f"研究问题：{item.research_question}")
                st.code(item.query, language=None)
                sort_label = SORT_LABELS.get(getattr(item, "sort", None), "相关度")
                counts = count_by_status(item.records)
                st.caption(
                    f"年份：{item.year_from or '不限'} — {item.year_to or '不限'} · "
                    f"条数：{item.retmax} · 排序：{sort_label} · "
                    f"PubMed 命中：{item.total_hits} · 已拉回：{len(item.records)}"
                )
                st.caption(
                    f"初筛：纳入 {counts['Include']} · 待定 {counts['Maybe']} · "
                    f"排除 {counts['Exclude']} · 未筛 {counts['Unscreened']}"
                )
                pmids = [record.pmid for record in item.records]
                with st.expander(f"已拉回 PMID（{len(pmids)}）", expanded=False):
                    st.code(", ".join(pmids) if pmids else "（无）", language=None)
                if st.button("打开此检索", key=f"open_history_{item.search_id}_{index}"):
                    st.session_state.records = [r.model_copy(deep=True) for r in item.records]
                    st.session_state.active_search = item
                    st.session_state.results_page = 0
                    st.session_state.results_status_filter = "未筛"
                    apply_search_to_form(item)
                    sync_active_search()
                    st.success("已载入。请到左侧点「结果」查看；搜索页已填回本次条件，可微调后再搜。")
                    st.rerun()
                if item.source_type == "pubmed_search" and st.button(
                    "Living Search：重新执行",
                    key=f"rerun_history_{item.search_id}_{index}",
                ):
                    try:
                        with st.spinner("正在重新执行 PubMed 检索…"):
                            fresh = run_search(
                                SearchParams(
                                    research_question=item.research_question,
                                    query=item.query,
                                    year_from=item.year_from,
                                    year_to=item.year_to,
                                    retmax=item.retmax,
                                    sort=item.sort,
                                    pico_population=item.pico_population,
                                    pico_intervention=item.pico_intervention,
                                    pico_comparator=item.pico_comparator,
                                    pico_outcome=item.pico_outcome,
                                    inclusion_criteria=item.inclusion_criteria,
                                    exclusion_criteria=item.exclusion_criteria,
                                ),
                                client=build_pubmed_client(),
                            )
                    except (PubMedConfigError, PubMedError, ValueError) as exc:
                        st.error(f"重新检索失败：{exc}")
                    else:
                        fresh.raw_query = item.raw_query
                        fresh.author_wrap_applied = item.author_wrap_applied
                        fresh.suggested_query = item.suggested_query
                        fresh.query_suggestion_blocks = item.query_suggestion_blocks
                        fresh.study_types = item.study_types
                        fresh.pico_ai_used = item.pico_ai_used
                        fresh.pico_ai_model = item.pico_ai_model
                        fresh.pico_ai_prompt_version = item.pico_ai_prompt_version
                        fresh.pico_ai_source_text = item.pico_ai_source_text
                        fresh.pico_ai_draft = item.pico_ai_draft
                        fresh.pico_ai_accepted = item.pico_ai_accepted
                        translations = translate_pubmed_query(item.query)
                        fresh.translated_wos = translation_text(translations, "wos")
                        fresh.translated_ebsco = translation_text(translations, "ebscohost")
                        fresh = _finalize_records(fresh)
                        merged = merge_living_search(item, fresh)
                        diff = compare_search_pmids(item, merged)
                        msg = (
                            f"Living Search 完成（新 ID: {merged.search_id}）。"
                            f" 新增 {diff.added_count} 篇，消失 {diff.removed_count} 篇，"
                            f"保留决策 {diff.common_count} 篇。"
                        )
                        _activate_search_result(merged, success_message=msg)

        _render_search_diff(history)

    st.divider()
    st.subheader("工作区备份")
    export_json = workspace_to_json(
        st.session_state.get("history", []),
        st.session_state.get("active_search"),
        st.session_state.get("ncbi_email"),
    )
    st.download_button(
        "导出工作区",
        data=export_json,
        file_name="evidence_copilot_workspace.json",
        mime="application/json",
    )

    uploaded = st.file_uploader("导入工作区（覆盖当前数据）", type=["json"])
    if uploaded is not None:
        if st.button("确认导入", type="primary"):
            try:
                workspace = workspace_from_json(uploaded.read().decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                st.error(f"无法读取工作区文件：{exc}")
                return
            st.session_state.history = workspace.history
            st.session_state.active_search = workspace.active_search
            st.session_state.records = workspace.records
            if workspace.ncbi_email:
                st.session_state.ncbi_email = workspace.ncbi_email
            st.session_state._workspace_corrupt = False
            try:
                save_workspace(
                    workspace.history,
                    workspace.active_search,
                    workspace.ncbi_email,
                )
            except OSError:
                st.warning("已导入到当前会话，但未能写入本地文件。")
            st.success("工作区已恢复。")
            st.rerun()


def _history_option_label(item: SearchResult) -> str:
    ts = item.executed_at.strftime("%Y-%m-%d %H:%M")
    return f"{ts} · ID {item.search_id} · {len(item.records)} 篇"


def _render_search_diff(history: list[SearchResult]) -> None:
    """对比两次检索的 PMID 差异。"""
    if len(history) < 2:
        return
    st.divider()
    st.subheader("检索对比")
    st.caption("选择两次检索，查看 PMID 新增、消失与共有（基于已拉回列表，不含未请求命中）。")
    options = list(reversed(history))
    labels = [_history_option_label(item) for item in options]
    col1, col2 = st.columns(2)
    with col1:
        first_label = st.selectbox("较早的检索", options=labels, index=1, key="diff_first")
    with col2:
        second_label = st.selectbox("较新的检索", options=labels, index=0, key="diff_second")
    if first_label == second_label:
        st.info("请选择两次不同的检索。")
        return
    first = options[labels.index(first_label)]
    second = options[labels.index(second_label)]
    diff = compare_search_pmids(first, second)
    m1, m2, m3 = st.columns(3)
    m1.metric("较新检索新增", diff.added_count)
    m2.metric("较新检索消失", diff.removed_count)
    m3.metric("两次共有", diff.common_count)
    with st.expander("查看 PMID 明细", expanded=False):
        st.markdown("**较新检索新增的 PMID**")
        st.code(", ".join(diff.only_in_second) if diff.only_in_second else "（无）", language=None)
        st.markdown("**较新检索消失的 PMID**")
        st.code(", ".join(diff.only_in_first) if diff.only_in_first else "（无）", language=None)
        st.markdown("**两次共有的 PMID**")
        st.code(", ".join(diff.in_both) if diff.in_both else "（无）", language=None)
