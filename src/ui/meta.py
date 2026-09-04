"""纳入文献人工提取与 PythonMeta 出图。"""

from __future__ import annotations

import io

import streamlit as st

from src.clients.deepseek import DeepSeekConfigError, DeepSeekError
from src.models.evidence import EvidenceRecord, ExtractionData
from src.services.extraction_suggest import (
    ExtractionDraft,
    apply_confirmed_draft,
    incomplete_included_records,
    suggest_extraction,
    suggest_extraction_from_document,
)
from src.services.fulltext import (
    FullTextConfigError,
    FullTextDocument,
    FullTextError,
    FullTextClient,
    extract_text_from_pdf,
)
from src.services.meta_analysis import (
    ALGORITHM_CATE,
    ALGORITHM_CONT,
    DATATYPE_CATE,
    DATATYPE_CONT,
    EFFECT_OPTIONS,
    MODEL_OPTIONS,
    default_study_label,
    extraction_is_complete,
    included_records,
    run_meta_analysis,
    update_extraction,
)
from src.ui.results import sync_active_search
from src.ui.setup import build_deepseek_client, has_deepseek_api_key

_SOURCE_LABELS = {
    "abstract": "摘要",
    "pmc": "PMC 全文",
    "unpaywall": "开放 PDF",
    "pdf_upload": "上传 PDF",
}

DATATYPE_LABELS = {"二分类": DATATYPE_CATE, "连续": DATATYPE_CONT}


def _parse_optional_int(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    return int(text)


def _parse_optional_float(raw: str) -> float | None:
    text = raw.strip()
    if not text:
        return None
    return float(text)


def _current_extraction(record: EvidenceRecord) -> ExtractionData:
    return record.extraction or ExtractionData()


def _outcome_hint() -> str:
    active = st.session_state.get("active_search")
    if active is not None and getattr(active, "pico_outcome", ""):
        return str(active.pico_outcome).strip()
    return str(st.session_state.get("search_pico_outcome") or "").strip()


def _drafts_store() -> dict[str, ExtractionDraft]:
    stored = st.session_state.get("extraction_drafts")
    if not isinstance(stored, dict):
        return {}
    return stored


def _fulltext_store() -> dict[str, FullTextDocument]:
    stored = st.session_state.get("fulltext_by_pmid")
    if not isinstance(stored, dict):
        return {}
    return stored


def _set_fulltext(pmid: str, document: FullTextDocument) -> None:
    store = dict(_fulltext_store())
    store[pmid] = document
    st.session_state.fulltext_by_pmid = store


def _widget_values_from_extraction(extraction: ExtractionData) -> dict[str, str]:
    """确认写入前要灌进输入框的字符串。"""
    values: dict[str, str] = {}
    if extraction.datatype == DATATYPE_CATE:
        values["e1"] = _num(extraction.e1)
        values["n1"] = _num(extraction.n1)
        values["e2"] = _num(extraction.e2)
        values["n2"] = _num(extraction.n2)
    elif extraction.datatype == DATATYPE_CONT:
        values["m1"] = _num(extraction.m1)
        values["sd1"] = _num(extraction.sd1)
        values["n1c"] = _num(extraction.n1)
        values["m2"] = _num(extraction.m2)
        values["sd2"] = _num(extraction.sd2)
        values["n2c"] = _num(extraction.n2)
    if extraction.study_label:
        values["label"] = extraction.study_label
    return values


def _apply_pending_extraction_fields() -> None:
    """在控件渲染前写入提取格子，避免 Streamlit 同轮无法改 widget。"""
    pending = st.session_state.pop("_extraction_apply", None)
    if not pending or not isinstance(pending, dict):
        return
    for pmid, fields in pending.items():
        if not isinstance(fields, dict):
            continue
        mapping = {
            "label": f"ext_label_{pmid}",
            "e1": f"ext_e1_{pmid}",
            "n1": f"ext_n1_{pmid}",
            "e2": f"ext_e2_{pmid}",
            "n2": f"ext_n2_{pmid}",
            "m1": f"ext_m1_{pmid}",
            "sd1": f"ext_sd1_{pmid}",
            "n1c": f"ext_n1c_{pmid}",
            "m2": f"ext_m2_{pmid}",
            "sd2": f"ext_sd2_{pmid}",
            "n2c": f"ext_n2c_{pmid}",
        }
        for key, widget_key in mapping.items():
            if key in fields:
                st.session_state[widget_key] = fields[key]


def _keep_ai_audit(updated: ExtractionData, previous: ExtractionData) -> ExtractionData:
    """手改数字时保留摘要草稿审计，并刷新确认后采用的数字。"""
    if not previous.ai_used:
        return updated
    accepted = {
        "datatype": updated.datatype,
        "e1": updated.e1,
        "n1": updated.n1,
        "e2": updated.e2,
        "n2": updated.n2,
        "m1": updated.m1,
        "sd1": updated.sd1,
        "m2": updated.m2,
        "sd2": updated.sd2,
    }
    return updated.model_copy(
        update={
            "ai_used": True,
            "ai_model": previous.ai_model,
            "ai_prompt_version": previous.ai_prompt_version,
            "ai_quote": previous.ai_quote,
            "ai_draft": previous.ai_draft,
            "ai_accepted": accepted,
            "subgroup": previous.subgroup,
        }
    )


def render_meta_page() -> None:
    """渲染 Meta 分析页。"""
    _apply_pending_extraction_fields()
    st.header("Meta 分析")
    st.caption(
        "只对「纳入」文献做合并。可从摘要或全文生成数字草稿，必须你核对确认后才写入；"
        "开放获取可自动拉取，付费全文请上传 PDF（如华西已购权限下载的文件）。"
        "缺数字保持空，不会当成 0。"
    )
    records: list[EvidenceRecord] = st.session_state.get("records") or []
    included = included_records(records)
    if not included:
        st.info("还没有纳入的文献。请先到「结果」页把可能合格的文献标为纳入。")
        return

    dtype_label = st.radio(
        "数据类型",
        options=list(DATATYPE_LABELS.keys()),
        horizontal=True,
        key="meta_datatype_label",
    )
    datatype = DATATYPE_LABELS[dtype_label]
    effect = st.selectbox("效应量", options=list(EFFECT_OPTIONS[datatype]), key="meta_effect")
    models = st.selectbox("效应模型", options=list(MODEL_OPTIONS), key="meta_models")
    algorithms = ALGORITHM_CATE if datatype == DATATYPE_CATE else ALGORITHM_CONT
    algorithm = st.selectbox("算法", options=list(algorithms), key="meta_algorithm")

    st.subheader("提取表")
    if datatype == DATATYPE_CATE:
        st.caption("二分类：干预组事件数 e1 / 人数 n1；对照组事件数 e2 / 人数 n2。")
    else:
        st.caption("连续：干预组均数 m1、标准差 sd1、人数 n1；对照组 m2、sd2、n2。")

    _render_suggest_controls(included, datatype)

    for record in included:
        _render_extraction_row(record, datatype)

    complete_n = sum(
        1
        for record in included_records(st.session_state.get("records") or [])
        if extraction_is_complete(record.extraction, datatype)
    )
    st.caption(f"纳入 {len(included)} 篇，提取完整 {complete_n} 篇。至少 2 篇完整才能计算。")

    if st.button("开始合并", type="primary", key="btn_run_meta"):
        sync_active_search()
        try:
            result = run_meta_analysis(
                st.session_state.get("records") or [],
                datatype=datatype,
                models=models,
                algorithm=algorithm,
                effect=effect,
                draw_plots=True,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"合并失败：{exc}")
            return
        st.session_state.meta_last_result = result
        st.success(f"已合并 {result.n_studies} 项研究。")

    result = st.session_state.get("meta_last_result")
    if result is None:
        return
    if result.skipped_pmids:
        st.warning(
            f"有 {len(result.skipped_pmids)} 篇纳入文献因提取不完整未进入合并："
            + ", ".join(result.skipped_pmids)
        )
    m1, m2, m3, m4 = st.columns(4)
    pooled = result.pooled_effect
    ci = ""
    if result.ci_low is not None and result.ci_high is not None:
        ci = f"（{result.ci_low:.2f}–{result.ci_high:.2f}）"
    m1.metric("合并效应", f"{pooled:.2f}{ci}" if pooled is not None else "—")
    m2.metric("I²", f"{result.i2:.1f}%" if result.i2 is not None else "—")
    m3.metric("研究数", result.n_studies)
    m4.metric("Q 检验 p", result.q_p or "—")
    st.text(result.text_table)
    if result.eggers:
        st.caption(f"Egger 检验：{result.eggers}")
    if result.forest_fig is not None:
        st.subheader("森林图")
        st.pyplot(result.forest_fig)
        st.download_button(
            "下载森林图 PNG",
            data=_fig_to_png(result.forest_fig),
            file_name="forest.png",
            mime="image/png",
            key="dl_forest",
        )
    if result.funnel_fig is not None:
        st.subheader("漏斗图")
        st.pyplot(result.funnel_fig)
        st.download_button(
            "下载漏斗图 PNG",
            data=_fig_to_png(result.funnel_fig),
            file_name="funnel.png",
            mime="image/png",
            key="dl_funnel",
        )


def _render_suggest_controls(included: list[EvidenceRecord], datatype: str) -> None:
    candidates = incomplete_included_records(included, datatype)
    with_fulltext = sum(1 for item in candidates if item.pmid in _fulltext_store())
    st.caption(
        f"未填全 {len(candidates)} 篇；其中已有全文 {with_fulltext} 篇。"
        "可先「批量拉取开放全文」或逐篇上传 PDF，再生成草稿；已填全的不会被覆盖。"
        "确认草稿不会自动开始合并。"
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("批量拉取开放全文", key="btn_fetch_open_fulltext"):
        _batch_fetch_open_fulltext(candidates)
    if c2.button("从全文生成提取草稿", key="btn_extraction_suggest_fulltext"):
        _start_extraction_suggest(candidates, datatype, prefer_fulltext=True)
    if c3.button("从摘要生成提取草稿", key="btn_extraction_suggest"):
        _start_extraction_suggest(candidates, datatype, prefer_fulltext=False)
    fetch_failures = st.session_state.get("fulltext_fetch_failures") or []
    if fetch_failures:
        st.warning(
            "部分文献未能拉取开放全文："
            + "；".join(f"{pmid}（{msg}）" for pmid, msg in fetch_failures)
        )
    failures = st.session_state.get("extraction_draft_failures") or []
    if failures:
        st.warning("部分文献未能生成草稿：" + "；".join(f"{pmid}（{msg}）" for pmid, msg in failures))


def _batch_fetch_open_fulltext(candidates: list[EvidenceRecord]) -> None:
    if not candidates:
        st.info("纳入文献都已填全，没有需要拉取全文的篇目。")
        return
    try:
        client = FullTextClient()
    except FullTextConfigError as exc:
        st.error(str(exc))
        return
    failures: list[tuple[str, str]] = []
    ok = 0
    total = len(candidates)
    with st.status("正在拉取开放全文（PMC / Unpaywall）…", expanded=True) as status:
        for index, record in enumerate(candidates, start=1):
            status.write(f"{index}/{total} PMID {record.pmid}")
            try:
                document = client.resolve_open_fulltext(pmid=record.pmid, doi=record.doi)
                _set_fulltext(record.pmid, document)
                ok += 1
            except FullTextError as exc:
                failures.append((record.pmid, str(exc)))
        status.update(label=f"开放全文完成：成功 {ok}，失败 {len(failures)}。", state="complete")
    st.session_state.fulltext_fetch_failures = failures
    st.rerun()


def _start_extraction_suggest(
    candidates: list[EvidenceRecord],
    datatype: str,
    *,
    prefer_fulltext: bool,
) -> None:
    if not candidates:
        st.info("纳入文献都已填全，没有需要生成草稿的篇目。")
        return
    if not has_deepseek_api_key():
        st.error("还没配置 DeepSeek 密钥。请先到「设置」填写，再生成提取草稿。")
        return
    try:
        client = build_deepseek_client()
    except DeepSeekConfigError as exc:
        st.error(str(exc))
        return
    outcome_hint = _outcome_hint()
    drafts = dict(_drafts_store())
    fulltexts = _fulltext_store()
    failures: list[tuple[str, str]] = []
    total = len(candidates)
    label = "正在从全文生成草稿（不会写入提取表）…" if prefer_fulltext else "正在从摘要生成草稿（不会写入提取表）…"
    with st.status(label, expanded=True) as status:
        for index, record in enumerate(candidates, start=1):
            status.write(f"{index}/{total} PMID {record.pmid}")
            try:
                document = fulltexts.get(record.pmid) if prefer_fulltext else None
                if document is not None:
                    drafts[record.pmid] = suggest_extraction_from_document(
                        pmid=record.pmid,
                        title=record.title,
                        abstract=record.abstract,
                        datatype=datatype,
                        document=document,
                        outcome_hint=outcome_hint,
                        complete_json=client.complete_json,
                        model=client.model,
                    )
                else:
                    if prefer_fulltext:
                        failures.append((record.pmid, "还没有全文，请先拉取或上传 PDF"))
                        continue
                    drafts[record.pmid] = suggest_extraction(
                        pmid=record.pmid,
                        title=record.title,
                        abstract=record.abstract,
                        datatype=datatype,
                        outcome_hint=outcome_hint,
                        complete_json=client.complete_json,
                        model=client.model,
                    )
            except DeepSeekError as exc:
                failures.append((record.pmid, str(exc)))
                continue
        status.update(label="草稿已生成，请逐篇核对。", state="complete")
    st.session_state.extraction_drafts = drafts
    st.session_state.extraction_draft_failures = failures
    st.rerun()


def _fig_to_png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    return buffer.getvalue()


def _render_draft_preview(record: EvidenceRecord, datatype: str) -> None:
    draft = _drafts_store().get(record.pmid)
    if draft is None or draft.datatype != datatype:
        return
    source_zh = _SOURCE_LABELS.get(draft.text_source, draft.text_source)
    st.info(f"提取草稿（来源：{source_zh}，尚未写入提取表）")
    if draft.has_any_number():
        if datatype == DATATYPE_CATE:
            st.caption(
                f"建议：e1={_num(draft.e1) or '空'}，n1={_num(draft.n1) or '空'}，"
                f"e2={_num(draft.e2) or '空'}，n2={_num(draft.n2) or '空'}"
            )
        else:
            st.caption(
                f"建议：m1={_num(draft.m1) or '空'}，sd1={_num(draft.sd1) or '空'}，"
                f"n1={_num(draft.n1) or '空'}；m2={_num(draft.m2) or '空'}，"
                f"sd2={_num(draft.sd2) or '空'}，n2={_num(draft.n2) or '空'}"
            )
    else:
        st.caption("正文里没有抽到完整数字，确认不会填入空值冒充 0。")
    if draft.quote:
        st.caption(f"原句：{draft.quote}")
    if draft.notes:
        st.caption(f"模型说明：{draft.notes}")
    confirm_col, discard_col = st.columns(2)
    if confirm_col.button("确认写入", key=f"ext_ai_confirm_{record.pmid}", disabled=not draft.has_any_number()):
        _confirm_draft(record, draft)
    if discard_col.button("丢弃草稿", key=f"ext_ai_discard_{record.pmid}"):
        _discard_draft(record.pmid)


def _confirm_draft(record: EvidenceRecord, draft: ExtractionDraft) -> None:
    label = record.extraction.study_label if record.extraction else None
    label = label or default_study_label(record)
    st.session_state.records = apply_confirmed_draft(
        st.session_state.get("records") or [],
        draft,
        study_label=label,
    )
    extraction = next(
        (item.extraction for item in st.session_state.records if item.pmid == record.pmid),
        None,
    )
    pending = dict(st.session_state.get("_extraction_apply") or {})
    if extraction is not None:
        pending[record.pmid] = _widget_values_from_extraction(extraction)
    st.session_state._extraction_apply = pending
    _discard_draft(record.pmid, rerun=False)
    sync_active_search()
    st.rerun()


def _discard_draft(pmid: str, *, rerun: bool = True) -> None:
    drafts = dict(_drafts_store())
    drafts.pop(pmid, None)
    st.session_state.extraction_drafts = drafts
    if rerun:
        st.rerun()


def _render_fulltext_controls(record: EvidenceRecord) -> None:
    """单篇：显示全文状态、拉取开放全文、上传 PDF。"""
    document = _fulltext_store().get(record.pmid)
    if document is not None:
        source_zh = _SOURCE_LABELS.get(document.source, document.source)
        st.caption(f"已有全文：{source_zh}，约 {document.char_count} 字。{document.notes}")
    else:
        st.caption(
            "尚无全文。「拉取本篇开放全文」只适用于免费开放文章；"
            "华西已购的付费全文，请先下载再上传 PDF。"
        )

    up_col, fetch_col = st.columns(2)
    uploaded = up_col.file_uploader(
        "上传本篇 PDF",
        type=["pdf"],
        key=f"fulltext_upload_{record.pmid}",
    )
    if uploaded is not None:
        # 避免同一文件反复解析：用 name+size 做标记
        marker_key = f"_fulltext_upload_done_{record.pmid}"
        marker = f"{uploaded.name}:{uploaded.size}"
        if st.session_state.get(marker_key) != marker:
            try:
                document = extract_text_from_pdf(uploaded.getvalue(), pmid=record.pmid)
                _set_fulltext(record.pmid, document)
                st.session_state[marker_key] = marker
                st.success(f"已读入 PDF（约 {document.char_count} 字）。")
                st.rerun()
            except FullTextError as exc:
                st.error(str(exc))
    if fetch_col.button("拉取本篇开放全文", key=f"fetch_ft_{record.pmid}"):
        try:
            client = FullTextClient()
            document = client.resolve_open_fulltext(pmid=record.pmid, doi=record.doi)
            _set_fulltext(record.pmid, document)
            st.rerun()
        except (FullTextConfigError, FullTextError) as exc:
            st.error(str(exc))


def _render_extraction_row(record: EvidenceRecord, datatype: str) -> None:
    ext = _current_extraction(record)
    with st.container(border=True):
        st.markdown(f"**{record.title}**")
        st.caption(f"PMID {record.pmid}")
        _render_fulltext_controls(record)
        _render_draft_preview(record, datatype)
        label_value = ext.study_label or default_study_label(record)
        study_label = st.text_input(
            "研究标签",
            value=label_value,
            key=f"ext_label_{record.pmid}",
        )
        if datatype == DATATYPE_CATE:
            c1, c2, c3, c4 = st.columns(4)
            e1_raw = c1.text_input("e1 干预组事件", value=_num(ext.e1), key=f"ext_e1_{record.pmid}")
            n1_raw = c2.text_input("n1 干预组人数", value=_num(ext.n1), key=f"ext_n1_{record.pmid}")
            e2_raw = c3.text_input("e2 对照组事件", value=_num(ext.e2), key=f"ext_e2_{record.pmid}")
            n2_raw = c4.text_input("n2 对照组人数", value=_num(ext.n2), key=f"ext_n2_{record.pmid}")
            try:
                updated = ExtractionData(
                    datatype=datatype,
                    study_label=study_label.strip() or None,
                    e1=_parse_optional_int(e1_raw),
                    n1=_parse_optional_int(n1_raw),
                    e2=_parse_optional_int(e2_raw),
                    n2=_parse_optional_int(n2_raw),
                )
            except ValueError:
                st.error("请填写整数，或留空。")
                return
        else:
            c1, c2, c3 = st.columns(3)
            c4, c5, c6 = st.columns(3)
            m1_raw = c1.text_input("m1 干预组均数", value=_num(ext.m1), key=f"ext_m1_{record.pmid}")
            sd1_raw = c2.text_input("sd1 干预组标准差", value=_num(ext.sd1), key=f"ext_sd1_{record.pmid}")
            n1_raw = c3.text_input("n1 干预组人数", value=_num(ext.n1), key=f"ext_n1c_{record.pmid}")
            m2_raw = c4.text_input("m2 对照组均数", value=_num(ext.m2), key=f"ext_m2_{record.pmid}")
            sd2_raw = c5.text_input("sd2 对照组标准差", value=_num(ext.sd2), key=f"ext_sd2_{record.pmid}")
            n2_raw = c6.text_input("n2 对照组人数", value=_num(ext.n2), key=f"ext_n2c_{record.pmid}")
            try:
                updated = ExtractionData(
                    datatype=datatype,
                    study_label=study_label.strip() or None,
                    m1=_parse_optional_float(m1_raw),
                    sd1=_parse_optional_float(sd1_raw),
                    n1=_parse_optional_int(n1_raw),
                    m2=_parse_optional_float(m2_raw),
                    sd2=_parse_optional_float(sd2_raw),
                    n2=_parse_optional_int(n2_raw),
                )
            except ValueError:
                st.error("请填写数字，或留空。")
                return
        updated = _keep_ai_audit(updated, ext)
        complete = extraction_is_complete(updated, datatype)
        if ext.ai_used:
            st.caption("提取完整（含已确认的 AI 草稿，可再手改）" if complete else "尚未填全，合并时将跳过本篇")
        else:
            st.caption("提取完整" if complete else "尚未填全，合并时将跳过本篇")
        st.session_state.records = update_extraction(
            st.session_state.records,
            record.pmid,
            updated,
        )


def _num(value: int | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
