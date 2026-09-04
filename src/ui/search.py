"""搜索页 UI。"""

from __future__ import annotations

import streamlit as st

from src.clients.deepseek import DeepSeekConfigError, DeepSeekError
from src.clients.pubmed import PubMedConfigError, PubMedError
from src.config.demo_search import DEMO_METFORMIN_RCT
from src.services.pico_extract import (
    accepted_pico_dict,
    extract_pico,
    join_concepts,
    needs_pico_extract,
)
from src.services.pubmed_url import map_sort_to_api, parse_pubmed_url, suggest_retmax
from src.services.query_builder import (
    author_wrap_applied,
    build_effective_query,
    can_wrap_author_field,
)
from src.services.query_lint import lint_pubmed_query
from src.services.query_suggest import (
    STUDY_TYPE_OPTIONS,
    format_suggestion_blocks,
    suggest_query,
)
from src.services.query_translate import translate_pubmed_query, translation_text
from src.services.import_records import (
    parse_nbib_file_bytes,
    parse_pmid_list,
    parse_ris_file_bytes,
)
from src.services.screening import dedupe_records, flag_potential_duplicates
from src.services.search import (
    ALLOWED_RETMAX,
    SearchParams,
    SearchResult,
    attempted_retrieved_count,
    create_import_result,
    merge_living_search,
    run_search,
)
from src.ui.setup import build_deepseek_client, build_pubmed_client, has_deepseek_api_key

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
    if "search_pico_population" not in st.session_state:
        st.session_state.search_pico_population = ""
    if "search_pico_intervention" not in st.session_state:
        st.session_state.search_pico_intervention = ""
    if "search_pico_comparator" not in st.session_state:
        st.session_state.search_pico_comparator = ""
    if "search_pico_outcome" not in st.session_state:
        st.session_state.search_pico_outcome = ""
    if "search_inclusion_criteria" not in st.session_state:
        st.session_state.search_inclusion_criteria = ""
    if "search_exclusion_criteria" not in st.session_state:
        st.session_state.search_exclusion_criteria = ""
    if "search_study_types" not in st.session_state:
        st.session_state.search_study_types = []


def _pico_kwargs() -> dict[str, str]:
    return {
        "pico_population": st.session_state.search_pico_population.strip(),
        "pico_intervention": st.session_state.search_pico_intervention.strip(),
        "pico_comparator": st.session_state.search_pico_comparator.strip(),
        "pico_outcome": st.session_state.search_pico_outcome.strip(),
        "inclusion_criteria": st.session_state.search_inclusion_criteria.strip(),
        "exclusion_criteria": st.session_state.search_exclusion_criteria.strip(),
    }


def _finalize_records(result: SearchResult) -> SearchResult:
    """去重、标记可能重复，写回 result.records。"""
    dedupe_result = dedupe_records(result.records)
    result.records = flag_potential_duplicates(dedupe_result.records)
    result.dedupe_removed_pmids = dedupe_result.removed_pmids or None
    return result


def _activate_search_result(result: SearchResult, *, success_message: str) -> None:
    """写入会话并追加历史。"""
    st.session_state.records = [r.model_copy(deep=True) for r in result.records]
    st.session_state.active_search = result
    st.session_state.results_page = 0
    st.session_state.results_status_filter = "未筛"
    st.session_state._workspace_corrupt = False
    history = st.session_state.get("history", [])
    history.append(result)
    st.session_state.history = history
    st.success(success_message)


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
    st.session_state.search_pico_population = "type 2 diabetes"
    st.session_state.search_pico_intervention = "metformin"
    st.session_state.search_pico_comparator = ""
    st.session_state.search_pico_outcome = ""
    st.session_state.search_inclusion_criteria = ""
    st.session_state.search_exclusion_criteria = ""
    st.session_state.search_study_types = ["rct"]


def _pico_has_values(pico: dict[str, str]) -> bool:
    return any(
        pico[key]
        for key in (
            "pico_population",
            "pico_intervention",
            "pico_comparator",
            "pico_outcome",
        )
    )


def _apply_pending_pico_fields() -> None:
    """在控件渲染前写入 PICO 格子，避免 Streamlit 同轮无法改 widget。"""
    pending = st.session_state.pop("_pico_apply", None)
    if not pending:
        return
    st.session_state.search_pico_population = pending.get("population") or ""
    st.session_state.search_pico_intervention = pending.get("intervention") or ""
    st.session_state.search_pico_comparator = pending.get("comparator") or ""
    st.session_state.search_pico_outcome = pending.get("outcome") or ""
    st.session_state.search_study_types = list(pending.get("study_types") or [])


def _attach_pico_ai_audit(result: SearchResult) -> None:
    """把本次会话里已确认的白话拆分记入检索记录。"""
    audit = st.session_state.get("pico_ai_audit") or {}
    if not audit.get("used"):
        return
    result.pico_ai_used = True
    result.pico_ai_model = audit.get("model")
    result.pico_ai_prompt_version = audit.get("prompt_version")
    result.pico_ai_source_text = audit.get("source_text")
    result.pico_ai_draft = audit.get("draft")
    result.pico_ai_accepted = audit.get("accepted")


def _refresh_pico_ai_accepted() -> None:
    audit = st.session_state.get("pico_ai_audit")
    if not isinstance(audit, dict) or not audit.get("used"):
        return
    pico = _pico_kwargs()
    audit["accepted"] = accepted_pico_dict(
        population=pico["pico_population"],
        intervention=pico["pico_intervention"],
        comparator=pico["pico_comparator"],
        outcome=pico["pico_outcome"],
        study_types=list(st.session_state.get("search_study_types") or []),
    )


def _run_mesh_suggestion(
    research_question: str,
    pico: dict[str, str],
    *,
    rerun: bool = True,
) -> None:
    """按当前 PICO 向 NCBI 查 MeSH 并生成建议式。"""
    try:
        with st.spinner("正在向 NCBI 查询 MeSH 词表（不会搜索文献）…"):
            client = build_pubmed_client()
            suggestion = suggest_query(
                population=pico["pico_population"],
                intervention=pico["pico_intervention"],
                comparator=pico["pico_comparator"],
                outcome=pico["pico_outcome"],
                study_types=list(st.session_state.search_study_types),
                research_question=research_question.strip(),
                lookup_mesh=client.lookup_mesh,
            )
    except PubMedConfigError:
        st.error("还没配置 NCBI 邮箱。请先到「设置」填写。")
        return
    except PubMedError as exc:
        st.error(f"MeSH 查词失败：{exc}")
        return
    _refresh_pico_ai_accepted()
    st.session_state.query_suggestion = suggestion
    st.session_state._suggest_notice = "已生成建议。请核对下方拼式后点「采用建议」。"
    if rerun:
        st.rerun()


def _start_pico_extract(research_question: str) -> None:
    """调用 DeepSeek 拆 PICO，写入预览草稿；不改检索框、不搜索。"""
    if not has_deepseek_api_key():
        st.error(
            "研究问题是中文白话，需要 DeepSeek 密钥才能拆成英文 PICO。"
            "请到「设置」填写密钥，或自己在 PICO 格子里填英文医学词。"
        )
        return
    try:
        with st.spinner("正在用 AI 拆 PICO（不会搜索文献、不会写入检索框）…"):
            client = build_deepseek_client()
            extraction = extract_pico(
                research_question,
                complete_json=client.complete_json,
                model=client.model,
            )
    except DeepSeekConfigError as exc:
        st.error(str(exc))
        return
    except DeepSeekError as exc:
        st.error(f"白话拆分失败：{exc}")
        return
    if not extraction.has_concepts():
        st.warning("模型没有拆出可用的 PICO 概念。请改写研究问题，或自己填写英文 PICO。")
        return
    st.session_state.pico_draft_population = join_concepts(extraction.population)
    st.session_state.pico_draft_intervention = join_concepts(extraction.intervention)
    st.session_state.pico_draft_comparator = join_concepts(extraction.comparator)
    st.session_state.pico_draft_outcome = join_concepts(extraction.outcome)
    st.session_state.pico_draft_study_types = list(extraction.study_types)
    st.session_state.pico_ai_extraction = extraction
    st.session_state._pico_ai_preview = True
    st.session_state._suggest_notice = "已拆出 PICO 草稿。请核对后点「确认并生成检索式」。"
    st.rerun()


def _confirm_pico_draft() -> None:
    """把预览草稿排进待写入队列，下一轮再填格子并查 MeSH。"""
    population = str(st.session_state.get("pico_draft_population") or "").strip()
    intervention = str(st.session_state.get("pico_draft_intervention") or "").strip()
    comparator = str(st.session_state.get("pico_draft_comparator") or "").strip()
    outcome = str(st.session_state.get("pico_draft_outcome") or "").strip()
    study_types = list(st.session_state.get("pico_draft_study_types") or [])
    if not (population or intervention or comparator or outcome):
        st.warning("草稿是空的，请至少保留一个概念。")
        return
    extraction = st.session_state.get("pico_ai_extraction")
    st.session_state.pico_ai_audit = {
        "used": True,
        "model": getattr(extraction, "model", "") or None,
        "prompt_version": getattr(extraction, "prompt_version", "") or None,
        "source_text": getattr(extraction, "source_text", "") or None,
        "draft": extraction.to_draft_dict() if extraction is not None else None,
        "accepted": accepted_pico_dict(
            population=population,
            intervention=intervention,
            comparator=comparator,
            outcome=outcome,
            study_types=study_types,
        ),
    }
    st.session_state._pico_apply = {
        "population": population,
        "intervention": intervention,
        "comparator": comparator,
        "outcome": outcome,
        "study_types": study_types,
    }
    st.session_state._pico_ai_preview = False
    st.session_state._pico_ai_pending_suggest = True
    st.rerun()


def _generate_query_suggestion(research_question: str) -> None:
    """按 PICO / 研究问题生成建议式；中文白话先拆 PICO。不搜索文献、不改检索框。"""
    pico = _pico_kwargs()
    has_pico = _pico_has_values(pico)
    if not has_pico and not research_question.strip():
        st.warning("请先填写 PICO 或研究问题。")
        return
    if needs_pico_extract(
        research_question,
        population=pico["pico_population"],
        intervention=pico["pico_intervention"],
        comparator=pico["pico_comparator"],
        outcome=pico["pico_outcome"],
    ):
        _start_pico_extract(research_question)
        return
    _run_mesh_suggestion(research_question, pico)


def _adopt_query_suggestion() -> None:
    """把已生成的建议写入检索框；不自动搜索。"""
    suggestion = st.session_state.get("query_suggestion")
    if suggestion is None or not suggestion.suggested_query.strip():
        st.warning("还没有可采用的建议。请先生成。")
        return
    st.session_state.search_query = suggestion.suggested_query
    st.session_state._suggest_notice = "已写入检索框。请再核对「将发送给 PubMed」，确认后才点搜索。"
    st.rerun()


def _render_suggestion_panel() -> None:
    """展示最近一次检索式建议。"""
    suggest_notice = st.session_state.pop("_suggest_notice", None)
    if suggest_notice:
        st.info(suggest_notice)
    suggestion = st.session_state.get("query_suggestion")
    if suggestion is None:
        return
    st.markdown("**建议检索式（尚未发送）**")
    if suggestion.suggested_query:
        st.code(suggestion.suggested_query, language=None)
    else:
        st.caption("建议为空。")
    st.markdown(format_suggestion_blocks(suggestion))
    if suggestion.unmatched_terms:
        st.warning(
            "以下词未匹配到官方 MeSH，已仅用题名/摘要字段："
            + "；".join(suggestion.unmatched_terms)
        )


def _render_pico_ai_preview() -> None:
    """展示 AI 拆出的 PICO 草稿；确认前不写入格子。"""
    if not st.session_state.get("_pico_ai_preview"):
        return
    extraction = st.session_state.get("pico_ai_extraction")
    st.markdown("**AI 拆出的 PICO（草稿，尚未写入上面的格子）**")
    st.caption(
        "请核对英文概念。多个概念用分号分隔。"
        "确认后才会填入 PICO 并去 NCBI 查官方主题词；不会自动搜索。"
    )
    if extraction is not None and getattr(extraction, "notes", ""):
        st.caption(f"模型说明：{extraction.notes}")
    with st.form("pico_ai_preview_form", clear_on_submit=False, border=True):
        p1, p2 = st.columns(2)
        with p1:
            st.text_area("P（人群）草稿", key="pico_draft_population", height=68)
            st.text_area("C（对照）草稿", key="pico_draft_comparator", height=68)
        with p2:
            st.text_area("I（干预）草稿", key="pico_draft_intervention", height=68)
            st.text_area("O（结局）草稿", key="pico_draft_outcome", height=68)
        st.multiselect(
            "研究类型草稿",
            options=list(STUDY_TYPE_OPTIONS.keys()),
            format_func=lambda key: STUDY_TYPE_OPTIONS[key][0],
            key="pico_draft_study_types",
        )
        confirm_col, discard_col = st.columns(2)
        with confirm_col:
            confirm = st.form_submit_button("确认并生成检索式", type="primary")
        with discard_col:
            discard = st.form_submit_button("放弃草稿")
        if confirm:
            _confirm_pico_draft()
        if discard:
            st.session_state._pico_ai_preview = False
            st.session_state._suggest_notice = "已放弃 AI 草稿。可改研究问题后重新生成。"
            st.rerun()


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
    st.session_state.search_pico_population = item.pico_population or ""
    st.session_state.search_pico_intervention = item.pico_intervention or ""
    st.session_state.search_pico_comparator = item.pico_comparator or ""
    st.session_state.search_pico_outcome = item.pico_outcome or ""
    st.session_state.search_inclusion_criteria = item.inclusion_criteria or ""
    st.session_state.search_exclusion_criteria = item.exclusion_criteria or ""
    st.session_state.search_study_types = list(item.study_types or [])


def render_search_page() -> None:
    """渲染搜索页。"""
    _init_search_form_state()
    _apply_pending_pico_fields()
    if st.session_state.pop("_pico_ai_pending_suggest", False):
        _run_mesh_suggestion(
            str(st.session_state.get("search_research_question") or ""),
            _pico_kwargs(),
            rerun=False,
        )
    st.header("搜索")
    st.caption(
        "填写检索式后，请先核对下方将发送给 PubMed 的内容，再执行搜索。"
        "在研究问题或 PICO 框里按 ⌘↩（Windows 为 Ctrl+Enter）会生成建议式，不会自动搜索；"
        "中文白话会先拆成英文 PICO 草稿，须确认后才查官方主题词。"
        "必须再点「采用建议」才写入检索框。"
    )

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

    # 表单才能让 ⌘↩ / Ctrl+Enter 触发「生成建议」；普通文本框里这个组合键只会刷新页面。
    with st.form("query_suggest_form", clear_on_submit=False, border=False, enter_to_submit=True):
        research_question = st.text_area(
            "研究问题（中文白话可先拆成 PICO；若已填 PICO 则只保存这段话）",
            height=80,
            key="search_research_question",
        )
        st.caption("焦点在本表单的输入框时，按 ⌘↩（Windows：Ctrl+Enter）= 生成建议，不是搜索文献。")

        with st.expander("PICO / 纳入排除标准（可选）", expanded=True):
            st.caption(
                "填写英文医学词可直接匹配官方 MeSH。"
                "若只写中文研究问题、四个格子都空，会先用 AI 拆成英文 PICO 草稿，须你确认。"
                "生成后请核对拼式，再点「采用建议」写入检索框；不会自动搜索。"
            )
            p1, p2 = st.columns(2)
            with p1:
                st.text_area("P（人群）", key="search_pico_population", height=68)
                st.text_area("C（对照）", key="search_pico_comparator", height=68)
            with p2:
                st.text_area("I（干预）", key="search_pico_intervention", height=68)
                st.text_area("O（结局）", key="search_pico_outcome", height=68)
            st.multiselect(
                "研究类型（写入检索式的类型块，可多选）",
                options=list(STUDY_TYPE_OPTIONS.keys()),
                format_func=lambda key: STUDY_TYPE_OPTIONS[key][0],
                key="search_study_types",
            )
            st.text_area("纳入标准", key="search_inclusion_criteria", height=68)
            st.text_area("排除标准", key="search_exclusion_criteria", height=68)

        gen_col, adopt_col = st.columns(2)
        with gen_col:
            generate = st.form_submit_button(
                "根据 PICO 生成检索式建议",
                key="btn_suggest_query",
                shortcut="Cmd+Enter",
                help="也可在研究问题或 PICO 框里按 ⌘↩ / Ctrl+Enter。不会自动搜索。",
            )
        with adopt_col:
            adopt = st.form_submit_button(
                "采用建议（写入检索框）",
                key="btn_adopt_query",
            )

        if generate:
            _generate_query_suggestion(research_question)
        if adopt:
            _adopt_query_suggestion()
        _render_suggestion_panel()

    _render_pico_ai_preview()

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

    if query.strip():
        lint_issues = lint_pubmed_query(effective_query or query)
        for issue in lint_issues:
            prefix = "错误" if issue.is_fatal else "提示"
            st.warning(f"检索式{prefix}（{issue.label}）：{issue.message}")

        with st.expander("翻译到其他数据库（仅供复制）", expanded=False):
            st.caption(
                "本工具仍只通过 PubMed 检索。下面的式子供你复制到 Web of Science / EBSCO 使用，"
                "不会改动上方检索式，也不会拿去搜索。当前不能自动翻译到 Embase。"
            )
            translations = translate_pubmed_query(effective_query or query)
            if not translations:
                st.caption("请先填写检索式。")
            for item in translations:
                st.markdown(f"**{item.label}**")
                if item.query:
                    st.code(item.query, language=None)
                else:
                    st.warning(item.error or "翻译失败。")

    with st.expander("导入已有检索结果（RIS / NBIB / PMID）", expanded=False):
        st.caption("在 PubMed 搜完后导出 RIS/NBIB，或粘贴 PMID 列表，在此导入后直接初筛。")
        import_tab_ris, import_tab_nbib, import_tab_pmid = st.tabs(["RIS 文件", "NBIB 文件", "PMID 列表"])
        with import_tab_ris:
            ris_file = st.file_uploader("上传 RIS 文件", type=["ris", "txt"], key="import_ris_file")
            if st.button("导入 RIS", key="btn_import_ris"):
                if ris_file is None:
                    st.warning("请先选择 RIS 文件。")
                else:
                    imported, missing_titles = parse_ris_file_bytes(ris_file.read())
                    if not imported:
                        st.error("未能从 RIS 中解析出含 PMID 的记录。")
                    else:
                        result = create_import_result(
                            imported,
                            research_question=research_question.strip(),
                            source_type="ris_import",
                            **_pico_kwargs(),
                        )
                        result = _finalize_records(result)
                        msg = f"已导入 {len(result.records)} 篇（ID: {result.search_id}）。请到「结果」初筛。"
                        if missing_titles:
                            st.warning(f"有 {len(missing_titles)} 条记录缺少 PMID，已跳过。")
                        _activate_search_result(result, success_message=msg)
        with import_tab_nbib:
            nbib_file = st.file_uploader("上传 NBIB 文件", type=["nbib", "txt"], key="import_nbib_file")
            if st.button("导入 NBIB", key="btn_import_nbib"):
                if nbib_file is None:
                    st.warning("请先选择 NBIB 文件。")
                else:
                    imported, missing_titles = parse_nbib_file_bytes(nbib_file.read())
                    if not imported:
                        st.error("未能从 NBIB 中解析出记录。")
                    else:
                        result = create_import_result(
                            imported,
                            research_question=research_question.strip(),
                            source_type="nbib_import",
                            **_pico_kwargs(),
                        )
                        result = _finalize_records(result)
                        msg = f"已导入 {len(result.records)} 篇（ID: {result.search_id}）。请到「结果」初筛。"
                        if missing_titles:
                            st.warning(f"有 {len(missing_titles)} 条记录缺少 PMID，已跳过。")
                        _activate_search_result(result, success_message=msg)
        with import_tab_pmid:
            pmid_text = st.text_area(
                "粘贴 PMID（逗号、空格或换行分隔）",
                height=100,
                key="import_pmid_text",
            )
            if st.button("按 PMID 导入", key="btn_import_pmid"):
                pmids = parse_pmid_list(pmid_text)
                if not pmids:
                    st.warning("请先粘贴至少一个 PMID。")
                else:
                    try:
                        with st.spinner("正在从 PubMed 补全元数据…"):
                            client = build_pubmed_client()
                            fetched, missing = client.fetch_by_pmids(pmids)
                    except PubMedConfigError:
                        st.error("还没配置 NCBI 邮箱。请先到「设置」填写。")
                        return
                    except PubMedError as exc:
                        st.error(f"PubMed 拉取失败：{exc}")
                        return
                    if not fetched:
                        st.error("未能拉回任何文献。")
                    else:
                        result = create_import_result(
                            fetched,
                            research_question=research_question.strip(),
                            query_label=f"PMID 列表导入（{len(fetched)} 篇）",
                            source_type="pmid_import",
                            **_pico_kwargs(),
                        )
                        result.missing_pmids = missing or None
                        result = _finalize_records(result)
                        msg = f"已导入 {len(result.records)} 篇（ID: {result.search_id}）。请到「结果」初筛。"
                        if missing:
                            st.warning(f"有 {len(missing)} 个 PMID 未能拉回元数据。")
                        _activate_search_result(result, success_message=msg)

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
                        **_pico_kwargs(),
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
        translations = translate_pubmed_query(effective_query)
        result.translated_wos = translation_text(translations, "wos")
        result.translated_ebsco = translation_text(translations, "ebscohost")
        suggestion = st.session_state.get("query_suggestion")
        if suggestion is not None:
            result.suggested_query = suggestion.suggested_query
            result.query_suggestion_blocks = suggestion.to_blocks_payload()
            result.study_types = list(suggestion.study_types)
        elif st.session_state.get("search_study_types"):
            result.study_types = list(st.session_state.search_study_types)
        _attach_pico_ai_audit(result)

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

        result = _finalize_records(result)
        if result.dedupe_removed_pmids:
            st.info(
                f"已去除 {len(result.dedupe_removed_pmids)} 篇重复（PMID/DOI 完全匹配），"
                "保留首次出现的记录。"
            )
            with st.expander("查看被去重的 PMID"):
                st.code(", ".join(result.dedupe_removed_pmids), language=None)

        attempted = attempted_retrieved_count(result)
        if result.total_hits > attempted:
            st.info(
                f"PubMed 共命中 {result.total_hits} 篇，本次拉回 {len(result.records)} 篇。"
                " 可在搜索页提高返回条数或缩小年份范围。"
            )

        if result.total_hits == 0:
            msg = f"搜索完成（ID: {result.search_id}），未找到文献。请到左侧点「结果」确认。"
        else:
            msg = f"搜索完成（ID: {result.search_id}）。请到左侧点「结果」查看文献并初筛。"
        _activate_search_result(result, success_message=msg)
