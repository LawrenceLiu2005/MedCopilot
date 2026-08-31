"""搜索页 UI。"""

from __future__ import annotations

import streamlit as st

from src.clients.pubmed import PubMedConfigError, PubMedError
from src.config.demo_search import DEMO_METFORMIN_RCT
from src.services.pubmed_url import map_sort_to_api, parse_pubmed_url, suggest_retmax
from src.services.query_builder import (
    author_wrap_applied,
    build_effective_query,
    can_wrap_author_field,
)
from src.services.screening import dedupe_records, flag_potential_duplicates
from src.services.search import ALLOWED_RETMAX, SearchParams, SearchResult, attempted_retrieved_count, run_search
from src.ui.setup import build_pubmed_client

SORT_OPTIONS: dict[str, str | None] = {
    "相关度": None,
    "发表日期": "pub_date",
}


def _init_search_form_state() -> None:
    if "search_research_question" not in st.session_state:
        st.session_state.search_research_question = ""
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""
    if "search_retmax" not in st.session_state:
        st.session_state.search_retmax = ALLOWED_RETMAX[0]
    if "search_year_from" not in st.session_state:
        st.session_state.search_year_from = 0
    if "search_year_to" not in st.session_state:
        st.session_state.search_year_to = 0
    if "search_sort" not in st.session_state:
        st.session_state.search_sort = SORT_OPTIONS["相关度"]
    if "search_author_field" not in st.session_state:
        st.session_state.search_author_field = False


def apply_demo_to_form() -> None:
    """填入固定演示检索主题（二甲双胍 RCT 示例）。"""
    demo = DEMO_METFORMIN_RCT
    st.session_state.search_research_question = demo.research_question
    st.session_state.search_query = demo.query
    st.session_state.search_year_from = demo.year_from
    st.session_state.search_year_to = demo.year_to
    st.session_state.search_retmax = demo.retmax if demo.retmax in ALLOWED_RETMAX else ALLOWED_RETMAX[0]
    st.session_state.search_sort = SORT_OPTIONS.get(demo.sort_label)
    st.session_state.search_sort_label = demo.sort_label
    st.session_state.search_author_field = False


def apply_search_to_form(item: SearchResult) -> None:
    """把一次历史检索填回搜索表单，便于微调后再搜。"""
    st.session_state.search_research_question = item.research_question or ""
    st.session_state.search_query = item.raw_query or item.query
    st.session_state.search_year_from = item.year_from or 0
    st.session_state.search_year_to = item.year_to or 0
    st.session_state.search_retmax = item.retmax if item.retmax in ALLOWED_RETMAX else ALLOWED_RETMAX[0]
    st.session_state.search_sort = item.sort
    st.session_state.search_sort_label = "发表日期" if item.sort == "pub_date" else "相关度"
    st.session_state.search_author_field = bool(item.author_wrap_applied)


def render_search_page() -> None:
    """渲染搜索页。"""
    _init_search_form_state()
    st.header("搜索")
    st.caption("填写检索式后，请先核对下方将发送给 PubMed 的内容，再执行搜索。")

    demo_col1, demo_col2 = st.columns([3, 1])
    with demo_col1:
        st.caption("首次试用？可一键填入示例检索（2 型糖尿病 + 二甲双胍 RCT，2020–2024，10 篇）。")
    with demo_col2:
        if st.button("填入示例检索"):
            apply_demo_to_form()
            st.session_state._demo_notice = "已填入示例。请核对下方检索式后点「搜索」。"
            st.rerun()

    demo_notice = st.session_state.pop("_demo_notice", None)
    if demo_notice:
        st.info(demo_notice)

    with st.expander("从 PubMed 链接导入", expanded=False):
        st.caption("粘贴 PubMed 网页搜索链接，自动填入检索式与选项（不会直接搜索）。")
        pubmed_url = st.text_input(
            "PubMed 网页链接",
            placeholder="https://pubmed.ncbi.nlm.nih.gov/?term=...",
            key="pubmed_import_url",
        )
        if st.button("导入链接"):
            imported = parse_pubmed_url(pubmed_url)
            if imported is None:
                st.error("无法识别该链接，请确认是 PubMed 搜索页并包含 term 参数。")
            else:
                st.session_state.search_query = imported.term
                st.session_state.search_retmax = suggest_retmax(imported.size_hint)
                st.session_state.search_sort = map_sort_to_api(imported.sort)
                st.session_state.search_sort_label = (
                    "发表日期" if imported.sort == "date" else "相关度"
                )
                st.session_state._url_import_notice = (
                    "已填入检索式。若 term 是作者姓名，可手动勾选「限定作者字段」。"
                )
                if imported.size_hint and imported.size_hint > ALLOWED_RETMAX[-1]:
                    st.warning(
                        f"网页显示 {imported.size_hint} 条，本项目一次最多拉 {ALLOWED_RETMAX[-1]} 条。"
                    )
                st.rerun()

    notice = st.session_state.pop("_url_import_notice", None)
    if notice:
        st.info(notice)

    research_question = st.text_area(
        "研究问题（仅保存，不会自动解析）",
        height=80,
        key="search_research_question",
    )
    query = st.text_area(
        "PubMed 检索式",
        height=100,
        placeholder='例如："diabetes"[Title] AND metformin[Title/Abstract]',
        key="search_query",
    )

    author_field = st.checkbox(
        "限定作者字段（将纯文本检索式包装为 \"姓名\"[Author]）",
        key="search_author_field",
    )
    if author_field and query.strip() and not can_wrap_author_field(query):
        st.caption("当前检索式含 PubMed 语法或布尔运算符，作者字段模式未生效。")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        year_from_raw = st.number_input(
            "年份起（0=不限）",
            min_value=0,
            max_value=2100,
            step=1,
            key="search_year_from",
        )
    with col2:
        year_to_raw = st.number_input(
            "年份止（0=不限）",
            min_value=0,
            max_value=2100,
            step=1,
            key="search_year_to",
        )
    with col3:
        retmax = st.selectbox(
            "返回条数",
            options=list(ALLOWED_RETMAX),
            key="search_retmax",
        )
    with col4:
        sort_labels = list(SORT_OPTIONS.keys())
        sort_label = st.selectbox(
            "排序",
            options=sort_labels,
            key="search_sort_label",
        )
    sort = SORT_OPTIONS[sort_label]

    year_from = int(year_from_raw) if year_from_raw > 0 else None
    year_to = int(year_to_raw) if year_to_raw > 0 else None
    sort_display = sort_label
    effective_query = build_effective_query(query, author_field=author_field)
    wrap_active = author_wrap_applied(query, author_field=author_field)

    st.markdown("**将发送给 PubMed**")
    preview_lines = [
        f"检索式: {effective_query or '（未填写）'}",
        f"年份筛选: {year_from or '不限'} — {year_to or '不限'}",
        f"返回条数: {retmax}",
        f"排序: {sort_display}",
    ]
    if wrap_active:
        preview_lines.insert(1, f"（原始输入: {query.strip()}）")
        st.warning("当前将按作者字段搜索，不是主题词。若你要搜疾病/主题，请取消勾选「限定作者字段」。")
    elif author_field and query.strip() and not can_wrap_author_field(query):
        preview_lines.insert(1, "（作者字段模式未生效，将使用原始检索式）")
    elif author_field and query.strip() and can_wrap_author_field(query):
        st.warning("当前将按作者字段搜索，不是主题词。若你要搜疾病/主题，请取消勾选「限定作者字段」。")
    st.code("\n".join(preview_lines), language=None)

    if st.button("搜索", type="primary"):
        if not query.strip():
            st.warning("请先填写 PubMed 检索式。")
            return
        try:
            with st.spinner("正在从 PubMed 拉取文献…"):
                result = run_search(
                    SearchParams(
                        research_question=research_question.strip(),
                        query=effective_query,
                        year_from=year_from,
                        year_to=year_to,
                        retmax=int(retmax),
                        sort=sort,
                    ),
                    client=build_pubmed_client(),
                )
        except PubMedConfigError:
            st.error("还没配置 NCBI 邮箱。请先到左侧「设置」填写后再搜索。")
            return
        except PubMedError as exc:
            st.error(f"PubMed 检索失败：{exc}")
            return
        except ValueError as exc:
            st.error(str(exc))
            return

        result.raw_query = query.strip() if wrap_active else None
        result.author_wrap_applied = wrap_active

        if result.total_hits == 0:
            st.warning(
                "PubMed 未找到匹配文献。请检查检索式、年份范围，或取消「限定作者字段」后再试。"
            )

        if result.missing_pmids:
            st.warning(
                f"有 {len(result.missing_pmids)} 篇文献的元数据未能从 PubMed 拉回，"
                " 结果列表可能不完整。"
            )
            with st.expander("查看未能拉回的 PMID"):
                st.code(", ".join(result.missing_pmids), language=None)

        dedupe_result = dedupe_records(result.records)
        if dedupe_result.removed_count > 0:
            st.info(
                f"已去除 {dedupe_result.removed_count} 篇重复（PMID/DOI 完全匹配），"
                "保留首次出现的记录。"
            )
            with st.expander("查看被去重的 PMID"):
                st.code(", ".join(dedupe_result.removed_pmids), language=None)

        result.records = flag_potential_duplicates(dedupe_result.records)
        result.dedupe_removed_pmids = dedupe_result.removed_pmids or None

        attempted = attempted_retrieved_count(result)
        if result.total_hits > attempted:
            st.info(
                f"PubMed 共命中 {result.total_hits} 篇，本次拉回 {len(result.records)} 篇。"
                " 可在搜索页提高返回条数或缩小年份范围。"
            )

        st.session_state.records = [r.model_copy(deep=True) for r in result.records]
        st.session_state.active_search = result
        st.session_state.results_page = 0
        st.session_state.results_status_filter = "未筛"
        st.session_state.search_author_field = False
        st.session_state._workspace_corrupt = False
        history = st.session_state.get("history", [])
        history.append(result)
        st.session_state.history = history
        if result.total_hits == 0:
            st.success(f"搜索完成（ID: {result.search_id}），未找到文献。请到左侧点「结果」确认。")
        else:
            st.success(f"搜索完成（ID: {result.search_id}）。请到左侧点「结果」查看文献并初筛。")
