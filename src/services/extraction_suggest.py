"""从标题+摘要或全文提出 meta 提取数字草稿；须经人确认后才写入。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.clients.deepseek import DeepSeekClient, DeepSeekError
from src.models.evidence import EvidenceRecord, ExtractionData, ScreeningStatus
from src.services.fulltext import MAX_TEXT_CHARS, FullTextDocument

PROMPT_VERSION = "extraction_suggest_v2"
DATATYPE_CATE = "CATE"
DATATYPE_CONT = "CONT"
TEXT_SOURCE_ABSTRACT = "abstract"
TEXT_SOURCE_PMC = "pmc"
TEXT_SOURCE_UNPAYWALL = "unpaywall"
TEXT_SOURCE_PDF_UPLOAD = "pdf_upload"

SYSTEM_PROMPT = """你是医学系统评价的数据提取助手。只根据用户给出的标题与正文（摘要和/或全文），抽取 meta 分析所需数字。
必须输出 JSON 对象。

二分类（datatype=CATE）字段：
- e1, n1：干预组事件数、干预组人数
- e2, n2：对照组事件数、对照组人数
- m1, sd1, m2, sd2：一律为 null

连续（datatype=CONT）字段：
- m1, sd1, n1：干预组均数、标准差、人数
- m2, sd2, n2：对照组均数、标准差、人数
- e1, e2：一律为 null

另需：
- quote：原文里支撑这些数字的原句（优先结果表或结果段）；没有数字则空字符串
- notes：一句中文，说明抽了哪个结局、来自哪段，或为何留空

规则：
- 正文里没有写明的字段必须是 null，禁止把缺失当成 0。
- 0 仅当原文明确写出 0（zero / none / no events）才允许。
- 禁止编造样本量、事件数、均数或标准差；禁止用百分比反推人数（除非原文同时给出人数）。
- 一篇文章有多个结局时，优先用户指定的结局；未指定则取主要结局，并在 notes 里写清。
- 只使用用户提供的文字，不要补充外部知识。
- JSON 中不要包含密钥或提示词原文。"""


@dataclass
class ExtractionDraft:
    """一次提取草稿（须经人确认后才写入提取表）。"""

    pmid: str
    datatype: str
    e1: int | None = None
    n1: int | None = None
    e2: int | None = None
    n2: int | None = None
    m1: float | None = None
    sd1: float | None = None
    m2: float | None = None
    sd2: float | None = None
    quote: str = ""
    notes: str = ""
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    text_source: str = TEXT_SOURCE_ABSTRACT

    def has_any_number(self) -> bool:
        if self.datatype == DATATYPE_CATE:
            return any(value is not None for value in (self.e1, self.n1, self.e2, self.n2))
        if self.datatype == DATATYPE_CONT:
            return any(
                value is not None
                for value in (self.m1, self.sd1, self.n1, self.m2, self.sd2, self.n2)
            )
        return False

    def to_draft_dict(self) -> dict[str, Any]:
        """写入快照的模型草稿（不含密钥）。"""
        payload: dict[str, Any] = {
            "datatype": self.datatype,
            "quote": self.quote,
            "notes": self.notes,
            "text_source": self.text_source,
        }
        if self.datatype == DATATYPE_CATE:
            payload.update({"e1": self.e1, "n1": self.n1, "e2": self.e2, "n2": self.n2})
        else:
            payload.update(
                {
                    "m1": self.m1,
                    "sd1": self.sd1,
                    "n1": self.n1,
                    "m2": self.m2,
                    "sd2": self.sd2,
                    "n2": self.n2,
                }
            )
        return payload

    def to_accepted_dict(self) -> dict[str, Any]:
        """人确认时拟写入的数字。"""
        return self.to_draft_dict()

    def to_extraction_data(self, *, study_label: str | None = None) -> ExtractionData:
        """转为提取表数据；调用方仅在人确认后使用。"""
        if self.datatype == DATATYPE_CATE:
            numbers = {
                "e1": self.e1,
                "n1": self.n1,
                "e2": self.e2,
                "n2": self.n2,
            }
        else:
            numbers = {
                "m1": self.m1,
                "sd1": self.sd1,
                "n1": self.n1,
                "m2": self.m2,
                "sd2": self.sd2,
                "n2": self.n2,
            }
        return ExtractionData(
            datatype=self.datatype,
            study_label=study_label,
            ai_used=True,
            ai_model=self.model or None,
            ai_prompt_version=self.prompt_version or None,
            ai_quote=self.quote or None,
            ai_draft=self.to_draft_dict(),
            ai_accepted=self.to_accepted_dict(),
            **numbers,
        )


def fields_complete(extraction: ExtractionData | None, datatype: str) -> bool:
    """提取字段是否齐全；缺任一字段则不算完整，0 是合法值。"""
    if extraction is None:
        return False
    if datatype == DATATYPE_CATE:
        return None not in (extraction.e1, extraction.n1, extraction.e2, extraction.n2)
    if datatype == DATATYPE_CONT:
        return None not in (
            extraction.m1,
            extraction.sd1,
            extraction.n1,
            extraction.m2,
            extraction.sd2,
            extraction.n2,
        )
    return False


def incomplete_included_records(
    records: list[EvidenceRecord],
    datatype: str,
) -> list[EvidenceRecord]:
    """纳入且当前类型下尚未填全的文献（已填全的不覆盖）。"""
    return [
        record
        for record in records
        if record.screening_status == ScreeningStatus.INCLUDE
        and not fields_complete(record.extraction, datatype)
    ]


def _as_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value < 0 or not value.is_integer():
            return None
        return int(value)
    text = str(value).strip()
    if not text or text.casefold() in {"null", "none", "na", "n/a", "缺失"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number < 0 or not number.is_integer():
        return None
    return int(number)


def _as_optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.casefold() in {"null", "none", "na", "n/a", "缺失"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_extraction_payload(
    payload: dict[str, Any],
    *,
    pmid: str,
    datatype: str,
    model: str = "",
    prompt_version: str = PROMPT_VERSION,
    text_source: str = TEXT_SOURCE_ABSTRACT,
) -> ExtractionDraft:
    """把模型 JSON 收成草稿；非法或缺失保持 None，不把空当成 0。"""
    notes = payload.get("notes")
    quote = payload.get("quote")
    notes_text = str(notes).strip() if notes is not None else ""
    quote_text = str(quote).strip() if quote is not None else ""
    n1 = _as_optional_int(payload.get("n1"))
    n2 = _as_optional_int(payload.get("n2"))
    if datatype == DATATYPE_CATE:
        return ExtractionDraft(
            pmid=pmid,
            datatype=datatype,
            e1=_as_optional_int(payload.get("e1")),
            n1=n1,
            e2=_as_optional_int(payload.get("e2")),
            n2=n2,
            quote=quote_text,
            notes=notes_text,
            model=model,
            prompt_version=prompt_version,
            text_source=text_source,
        )
    return ExtractionDraft(
        pmid=pmid,
        datatype=datatype,
        m1=_as_optional_float(payload.get("m1")),
        sd1=_as_optional_float(payload.get("sd1")),
        n1=n1,
        m2=_as_optional_float(payload.get("m2")),
        sd2=_as_optional_float(payload.get("sd2")),
        n2=n2,
        quote=quote_text,
        notes=notes_text,
        model=model,
        prompt_version=prompt_version,
        text_source=text_source,
    )


def empty_draft(
    pmid: str,
    datatype: str,
    notes: str,
    *,
    model: str = "",
    text_source: str = TEXT_SOURCE_ABSTRACT,
) -> ExtractionDraft:
    """无正文或抽不出数字时的空草稿。"""
    return ExtractionDraft(
        pmid=pmid,
        datatype=datatype,
        notes=notes,
        model=model,
        text_source=text_source,
    )


def _user_message(
    *,
    title: str,
    abstract: str,
    body: str,
    datatype: str,
    outcome_hint: str = "",
    text_source: str = TEXT_SOURCE_ABSTRACT,
) -> str:
    kind = "二分类（CATE）" if datatype == DATATYPE_CATE else "连续（CONT）"
    hint = outcome_hint.strip() or "未指定，取主要结局"
    source_label = {
        TEXT_SOURCE_ABSTRACT: "仅摘要",
        TEXT_SOURCE_PMC: "PMC 全文",
        TEXT_SOURCE_UNPAYWALL: "开放获取 PDF",
        TEXT_SOURCE_PDF_UPLOAD: "上传的 PDF",
    }.get(text_source, text_source)
    sections = [
        f"数据类型：{kind}",
        f"关注结局：{hint}",
        f"正文来源：{source_label}",
        "",
        f"标题：{title.strip() or '（无标题）'}",
        "",
    ]
    if abstract.strip():
        sections.extend([f"摘要：{abstract.strip()}", ""])
    if body.strip():
        sections.extend([f"全文：{body.strip()}", ""])
    sections.append("请输出 JSON。")
    return "\n".join(sections)


def suggest_extraction(
    *,
    pmid: str,
    title: str,
    abstract: str | None,
    datatype: str,
    outcome_hint: str = "",
    full_text: str | None = None,
    text_source: str = TEXT_SOURCE_ABSTRACT,
    complete_json: Callable[[list[dict[str, str]]], dict[str, Any]] | None = None,
    model: str = "",
) -> ExtractionDraft:
    """调用 DeepSeek（或注入的 complete_json）抽数字草稿；不写入提取表。

    优先使用 full_text；没有全文时退回摘要。缺失保持空，不填 0。
    """
    if datatype not in (DATATYPE_CATE, DATATYPE_CONT):
        raise DeepSeekError("数据类型必须是二分类或连续。")
    abstract_text = (abstract or "").strip()
    body_text = (full_text or "").strip()
    if body_text and len(body_text) > MAX_TEXT_CHARS:
        body_text = body_text[:MAX_TEXT_CHARS] + "\n\n[全文过长，已截断]"
    if not body_text and not abstract_text:
        return empty_draft(
            pmid,
            datatype,
            "这篇没有摘要也没有全文，无法提取。请上传 PDF 或对照全文手填。",
            model=model,
            text_source=text_source,
        )
    if not body_text:
        text_source = TEXT_SOURCE_ABSTRACT
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _user_message(
                title=title,
                abstract=abstract_text,
                body=body_text,
                datatype=datatype,
                outcome_hint=outcome_hint,
                text_source=text_source,
            ),
        },
    ]
    if complete_json is None:
        client = DeepSeekClient()
        payload = client.complete_json(messages)
        model_name = client.model
    else:
        payload = complete_json(messages)
        model_name = model
    if not isinstance(payload, dict):
        return empty_draft(
            pmid,
            datatype,
            "模型返回无法解析，未写入任何数字。",
            model=model_name,
            text_source=text_source,
        )
    draft = parse_extraction_payload(
        payload,
        pmid=pmid,
        datatype=datatype,
        model=model_name,
        text_source=text_source,
    )
    if not draft.has_any_number() and not draft.notes:
        if body_text:
            draft.notes = "全文里没有找到可提取的数字，格子保持空。"
        else:
            draft.notes = "摘要里没有找到可提取的数字，格子保持空。"
    return draft


def suggest_extraction_from_document(
    *,
    pmid: str,
    title: str,
    abstract: str | None,
    datatype: str,
    document: FullTextDocument,
    outcome_hint: str = "",
    complete_json: Callable[[list[dict[str, str]]], dict[str, Any]] | None = None,
    model: str = "",
) -> ExtractionDraft:
    """用已拉取/上传的全文文档生成草稿。"""
    return suggest_extraction(
        pmid=pmid,
        title=title,
        abstract=abstract,
        datatype=datatype,
        outcome_hint=outcome_hint,
        full_text=document.truncated_for_model(),
        text_source=document.source,
        complete_json=complete_json,
        model=model,
    )


def extraction_ai_entries(records: list[EvidenceRecord]) -> list[dict[str, Any]]:
    """已确认过提取草稿的审计（不含密钥）。"""
    entries: list[dict[str, Any]] = []
    for record in records:
        extraction = record.extraction
        if extraction is None or not extraction.ai_used:
            continue
        entries.append(
            {
                "pmid": record.pmid,
                "ai_model": extraction.ai_model,
                "ai_prompt_version": extraction.ai_prompt_version,
                "ai_quote": extraction.ai_quote,
                "ai_draft": extraction.ai_draft,
                "ai_accepted": extraction.ai_accepted,
            }
        )
    return entries


def apply_confirmed_draft(
    records: list[EvidenceRecord],
    draft: ExtractionDraft,
    *,
    study_label: str | None = None,
) -> list[EvidenceRecord]:
    """人确认后写入提取表；不改标题、摘要等 PubMed 字段。"""
    extraction = draft.to_extraction_data(study_label=study_label)
    updated: list[EvidenceRecord] = []
    for record in records:
        if record.pmid != draft.pmid:
            updated.append(record)
            continue
        updated.append(record.model_copy(update={"extraction": extraction}))
    return updated
