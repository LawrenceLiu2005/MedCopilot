"""开放获取全文拉取与 PDF 抽字；不绕过付费墙。"""

from __future__ import annotations

import io
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx
from pypdf import PdfReader
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config.ncbi_credentials import resolve_ncbi_api_key, resolve_ncbi_email

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
TIMEOUT = 45.0
MAX_TEXT_CHARS = 60_000
SOURCE_PMC = "pmc"
SOURCE_UNPAYWALL = "unpaywall"
SOURCE_PDF_UPLOAD = "pdf_upload"


class FullTextError(Exception):
    """全文获取或解析失败。"""


class FullTextConfigError(FullTextError):
    """缺少邮箱等配置。"""


@dataclass
class FullTextDocument:
    """一篇可用的全文文本（供提取草稿用，不永久写入库）。"""

    pmid: str
    source: str
    text: str
    pmcid: str | None = None
    doi: str | None = None
    pdf_url: str | None = None
    notes: str = ""

    @property
    def char_count(self) -> int:
        return len(self.text)

    def truncated_for_model(self, limit: int = MAX_TEXT_CHARS) -> str:
        """超长全文截断，优先保留前半（常含方法与结果）。"""
        cleaned = self.text.strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit] + "\n\n[全文过长，已截断]"


def extract_text_from_pdf(data: bytes, *, pmid: str = "") -> FullTextDocument:
    """从 PDF 字节抽出纯文本；抽不出则报错。"""
    if not data:
        raise FullTextError("PDF 文件为空。")
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise FullTextError(f"无法打开 PDF：{exc}") from exc
    parts: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            parts.append(page_text)
    text = "\n\n".join(parts).strip()
    if not text:
        raise FullTextError("PDF 里抽不出文字（可能是扫描件）。请手填或换可复制文字的 PDF。")
    return FullTextDocument(
        pmid=pmid,
        source=SOURCE_PDF_UPLOAD,
        text=text,
        notes=f"本地上传 PDF，共 {len(reader.pages)} 页。",
    )


def _throttle_pause(last_at: list[float], min_interval: float) -> None:
    elapsed = time.monotonic() - last_at[0]
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    last_at[0] = time.monotonic()


class FullTextClient:
    """优先 PMC XML，其次 Unpaywall 开放 PDF；不访问付费墙。"""

    def __init__(
        self,
        email: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = TIMEOUT,
    ) -> None:
        self.email = (email or resolve_ncbi_email() or "").strip()
        if api_key is not None:
            self.api_key = api_key.strip() or None
        else:
            self.api_key = resolve_ncbi_api_key()
        if not self.email:
            raise FullTextConfigError("缺少邮箱（NCBI_EMAIL），拉取开放全文需要邮箱。")
        self.timeout = timeout
        self._min_interval = 0.11 if self.api_key else 0.34
        self._last_request_at = [0.0]

    def resolve_open_fulltext(
        self,
        *,
        pmid: str,
        doi: str | None = None,
    ) -> FullTextDocument:
        """按 PMID 尝试 PMC，再按 DOI 尝试 Unpaywall；都失败则抛错。"""
        errors: list[str] = []
        try:
            return self.fetch_pmc_by_pmid(pmid)
        except FullTextError as exc:
            errors.append(str(exc))
        if doi and doi.strip():
            try:
                return self.fetch_unpaywall_pdf(doi.strip(), pmid=pmid)
            except FullTextError as exc:
                errors.append(str(exc))
        detail = "；".join(errors) if errors else "无开放全文"
        raise FullTextError(
            f"未能自动获取开放全文（PMID {pmid}）。{detail}。"
            "说明：此按钮只拉免费开放全文（PMC / Unpaywall），"
            "不会使用华西订购权限。付费文章请在浏览器下载后点「上传本篇 PDF」。"
        )

    def fetch_pmc_by_pmid(self, pmid: str) -> FullTextDocument:
        """ELink 找 PMCID，再 EFetch XML 抽正文。"""
        pmcid = self.lookup_pmcid(pmid)
        if not pmcid:
            raise FullTextError("PubMed 未关联 PMC 全文")
        return self.fetch_pmc_xml(pmcid, pmid=pmid)

    def lookup_pmcid(self, pmid: str) -> str | None:
        """PMID → PMCID（带 PMC 前缀）；没有则 None。"""
        cleaned = str(pmid).strip()
        if not cleaned:
            return None
        response = self._ncbi_get(
            "elink.fcgi",
            {
                "dbfrom": "pubmed",
                "db": "pmc",
                "id": cleaned,
                "retmode": "json",
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FullTextError("PMC 链接返回格式异常") from exc
        return _pmcid_from_elink(payload)

    def fetch_pmc_xml(self, pmcid: str, *, pmid: str = "") -> FullTextDocument:
        """拉取 PMC 全文 XML 并抽文字。"""
        numeric = pmcid.upper().removeprefix("PMC")
        response = self._ncbi_get(
            "efetch.fcgi",
            {"db": "pmc", "id": numeric, "rettype": "xml", "retmode": "xml"},
        )
        text = extract_text_from_pmc_xml(response.text)
        if not text.strip():
            raise FullTextError(f"PMC{numeric} 全文 XML 为空或无法解析")
        return FullTextDocument(
            pmid=pmid,
            source=SOURCE_PMC,
            text=text,
            pmcid=f"PMC{numeric}",
            notes="来自 PubMed Central 开放全文。",
        )

    def fetch_unpaywall_pdf(self, doi: str, *, pmid: str = "") -> FullTextDocument:
        """Unpaywall 查开放 PDF 链接并下载抽字。"""
        doi_clean = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        if not doi_clean:
            raise FullTextError("缺少 DOI，无法查 Unpaywall")
        url = f"{UNPAYWALL_BASE}/{doi_clean}"
        try:
            response = httpx.get(
                url,
                params={"email": self.email},
                timeout=self.timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise FullTextError(f"Unpaywall 网络失败：{exc}") from exc
        if response.status_code == 404:
            raise FullTextError("Unpaywall 未找到该 DOI")
        if response.status_code >= 400:
            raise FullTextError(f"Unpaywall 请求失败：HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise FullTextError("Unpaywall 返回格式异常") from exc
        pdf_url = _best_oa_pdf_url(payload)
        if not pdf_url:
            raise FullTextError("Unpaywall 无开放 PDF 链接")
        pdf_bytes = self._download_bytes(pdf_url)
        doc = extract_text_from_pdf(pdf_bytes, pmid=pmid)
        return FullTextDocument(
            pmid=pmid,
            source=SOURCE_UNPAYWALL,
            text=doc.text,
            doi=doi_clean,
            pdf_url=pdf_url,
            notes="来自 Unpaywall 开放获取 PDF。",
        )

    def _download_bytes(self, url: str) -> bytes:
        try:
            response = httpx.get(url, timeout=self.timeout, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise FullTextError(f"下载 PDF 失败：{exc}") from exc
        if response.status_code >= 400:
            raise FullTextError(f"下载 PDF 失败：HTTP {response.status_code}")
        content_type = (response.headers.get("content-type") or "").lower()
        data = response.content
        if "pdf" not in content_type and not data[:5].startswith(b"%PDF"):
            raise FullTextError("下载内容不是 PDF（可能被登录页拦截）")
        return data

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, FullTextError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _ncbi_get(self, endpoint: str, params: dict[str, Any]) -> httpx.Response:
        _throttle_pause(self._last_request_at, self._min_interval)
        merged = {"email": self.email, **params}
        if self.api_key:
            merged["api_key"] = self.api_key
        try:
            response = httpx.get(
                f"{EUTILS_BASE}/{endpoint}",
                params=merged,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise FullTextError(f"NCBI 网络失败：{exc}") from exc
        if response.status_code >= 500:
            raise FullTextError(f"NCBI 服务器错误：HTTP {response.status_code}")
        if response.status_code >= 400:
            raise FullTextError(f"NCBI 请求被拒绝：HTTP {response.status_code}")
        return response


def _pmcid_from_elink(payload: dict[str, Any]) -> str | None:
    """只取 pubmed→pmc 的正文链接；忽略 pubmed_pmc_refs（被谁引用）。"""
    try:
        linksets = payload["linksets"]
        if not linksets:
            return None
        dbs = linksets[0].get("linksetdbs") or []
        preferred: str | None = None
        for db in dbs:
            if str(db.get("dbto", "")).lower() != "pmc":
                continue
            linkname = str(db.get("linkname") or "").lower()
            # pubmed_pmc_refs = 引用了本文的 PMC 文章，不是本文全文
            if linkname.endswith("_refs") or "refs" in linkname:
                continue
            ids = db.get("links") or []
            if not ids:
                continue
            numeric = str(ids[0]).strip()
            if not numeric:
                continue
            pmcid = f"PMC{numeric}" if not numeric.upper().startswith("PMC") else numeric.upper()
            if linkname == "pubmed_pmc":
                return pmcid
            if preferred is None:
                preferred = pmcid
        return preferred
    except (KeyError, TypeError, IndexError):
        return None
    return None

def _best_oa_pdf_url(payload: dict[str, Any]) -> str | None:
    """取 Unpaywall 最佳开放 PDF URL。"""
    candidates: list[dict[str, Any]] = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        candidates.append(best)
    locations = payload.get("oa_locations") or []
    if isinstance(locations, list):
        candidates.extend(item for item in locations if isinstance(item, dict))
    for item in candidates:
        url = item.get("url_for_pdf") or item.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def extract_text_from_pmc_xml(xml_text: str) -> str:
    """从 PMC 全文 XML 抽出可读正文（含表格单元格）。"""
    cleaned = xml_text.strip()
    if not cleaned:
        return ""
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        # 偶发前缀噪音，尝试截到第一个 <
        start = cleaned.find("<")
        if start < 0:
            return ""
        try:
            root = ET.fromstring(cleaned[start:])
        except ET.ParseError:
            return ""

    parts: list[str] = []
    # 标题
    for title in root.iter():
        if _local(title.tag) in {"article-title", "title"} and title.text:
            text = _element_text(title).strip()
            if text:
                parts.append(text)
                break
    # 摘要
    for abstract in root.iter():
        if _local(abstract.tag) == "abstract":
            text = _element_text(abstract).strip()
            if text:
                parts.append("摘要\n" + text)
            break
    # 正文段落与小节标题
    body = None
    for node in root.iter():
        if _local(node.tag) == "body":
            body = node
            break
    if body is not None:
        for node in body.iter():
            tag = _local(node.tag)
            if tag in {"p", "title", "label"}:
                text = "".join(node.itertext()).strip()
                text = re.sub(r"\s+", " ", text)
                if text:
                    parts.append(text)
            elif tag == "table":
                table_text = _table_text(node)
                if table_text:
                    parts.append(table_text)
    else:
        # 无 body 时退化为整棵树纯文本
        fallback = re.sub(r"\s+", " ", "".join(root.itertext())).strip()
        if fallback:
            parts.append(fallback)

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        unique.append(part)
    return "\n\n".join(unique).strip()


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _element_text(node: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def _table_text(table: ET.Element) -> str:
    rows: list[str] = []
    for row in table.iter():
        if _local(row.tag) != "tr":
            continue
        cells: list[str] = []
        for cell in list(row):
            if _local(cell.tag) not in {"td", "th"}:
                continue
            cells.append(_element_text(cell))
        if cells:
            rows.append(" | ".join(cells))
    if not rows:
        return ""
    return "表格\n" + "\n".join(rows)
