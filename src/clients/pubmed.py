"""PubMed E-utilities 客户端。"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config.ncbi_credentials import resolve_ncbi_api_key, resolve_ncbi_email
from src.models.evidence import EvidenceRecord

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TIMEOUT = 30.0
MAX_MESH_ENTRY_TERMS = 5
MESH_LOOKUP_CANDIDATES = 5


class PubMedError(Exception):
    """PubMed API 调用失败。"""


class PubMedConfigError(PubMedError):
    """配置缺失或无效。"""


@dataclass(frozen=True)
class MeshLookupResult:
    """NCBI MeSH 词表匹配结果；未匹配时 descriptor 为 None，不编造。"""

    query: str
    matched: bool
    descriptor: str | None = None
    mesh_id: str | None = None
    entry_terms: tuple[str, ...] = ()
    field_tag: str = "MeSH Terms"


class PubMedClient:
    """NCBI E-utilities 客户端：ESearch → EFetch。"""

    def __init__(self, email: str | None = None, api_key: str | None = None) -> None:
        self.email = (email or resolve_ncbi_email() or "").strip()
        if api_key is not None:
            self.api_key = api_key.strip() or None
        else:
            self.api_key = resolve_ncbi_api_key()
        if not self.email:
            raise PubMedConfigError("缺少 NCBI 邮箱，请在设置页或 .env 中配置。")
        # ponytail: 简单 sleep 限速；无 key 约 3 req/s，有 key 约 10 req/s
        self._min_interval = 0.11 if self.api_key else 0.34
        self._last_request_at = 0.0

    def search(
        self,
        query: str,
        *,
        retmax: int = 10,
        mindate: str | None = None,
        maxdate: str | None = None,
        sort: str | None = None,
    ) -> tuple[int, list[EvidenceRecord], list[str]]:
        """检索 PubMed，返回 (总命中数, 文献列表, 元数据拉取失败的 PMID)。"""
        total, pmids = self._esearch(
            query, retmax=retmax, mindate=mindate, maxdate=maxdate, sort=sort
        )
        if not pmids:
            return total, [], []
        articles = self._efetch(pmids)
        fetched_pmids = {str(a["pmid"]) for a in articles}
        missing_pmids = [pmid for pmid in pmids if pmid not in fetched_pmids]
        records = [EvidenceRecord.from_pubmed_dict(a) for a in articles]
        return total, records, missing_pmids

    def fetch_by_pmids(self, pmids: list[str]) -> tuple[list[EvidenceRecord], list[str]]:
        """按 PMID 列表拉回元数据，返回 (文献列表, 未能拉回的 PMID)。"""
        cleaned = [str(p).strip() for p in pmids if str(p).strip()]
        if not cleaned:
            return [], []
        articles = self._efetch(cleaned)
        fetched_pmids = {str(a["pmid"]) for a in articles}
        missing_pmids = [pmid for pmid in cleaned if pmid not in fetched_pmids]
        records = [EvidenceRecord.from_pubmed_dict(a) for a in articles]
        return records, missing_pmids

    def lookup_mesh(self, term: str) -> MeshLookupResult:
        """在 NCBI MeSH 词表中查找官方主题词与入口词；查不到则 matched=False。

        NCBI 对 db=mesh 的 EFetch 常返回纯文本，因此用 ESummary JSON。
        多个候选时只采用词表项能对上用户原文的记录，不取「相关但不同」的第一条。
        解析失败不抛错，视为未匹配，避免整条建议中断。
        """
        cleaned = " ".join(term.split())
        if not cleaned:
            return MeshLookupResult(query=term, matched=False)
        ids = self._esearch_ids(cleaned, db="mesh", retmax=MESH_LOOKUP_CANDIDATES)
        if not ids:
            return MeshLookupResult(query=cleaned, matched=False)
        try:
            response = self._get(
                "esummary.fcgi",
                {"db": "mesh", "id": ",".join(ids), "retmode": "json"},
            )
            payload = response.json()
        except (PubMedError, ValueError, TypeError):
            return MeshLookupResult(query=cleaned, matched=False)
        summaries = _mesh_summaries_from_payload(payload, ids)
        selected = select_best_mesh_summary(cleaned, summaries)
        if selected is None:
            return MeshLookupResult(query=cleaned, matched=False)
        item, parsed = selected
        descriptor, field_tag, entry_terms = parsed
        filtered = _filter_entry_terms(descriptor, cleaned, entry_terms)
        mesh_ui = str(item.get("ds_meshui") or item.get("uid") or "").strip() or None
        return MeshLookupResult(
            query=cleaned,
            matched=True,
            descriptor=descriptor,
            mesh_id=mesh_ui,
            entry_terms=tuple(filtered),
            field_tag=field_tag,
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _base_params(self) -> dict[str, str]:
        params: dict[str, str] = {"email": self.email}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, PubMedError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _get(self, endpoint: str, params: dict[str, Any]) -> httpx.Response:
        self._throttle()
        url = f"{EUTILS_BASE}/{endpoint}"
        merged = {**self._base_params(), **params}
        try:
            response = httpx.get(url, params=merged, timeout=TIMEOUT)
        except httpx.HTTPError as exc:
            raise PubMedError(f"PubMed 网络请求失败: {exc}") from exc
        if response.status_code >= 500:
            raise PubMedError(f"PubMed 服务器错误: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise PubMedError(f"PubMed 请求被拒绝: HTTP {response.status_code}")
        return response

    def _esearch(
        self,
        query: str,
        *,
        retmax: int,
        mindate: str | None,
        maxdate: str | None,
        sort: str | None = None,
    ) -> tuple[int, list[str]]:
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
        }
        if sort:
            params["sort"] = sort
        if mindate:
            params["mindate"] = mindate
        if maxdate:
            params["maxdate"] = maxdate
        if mindate or maxdate:
            params["datetype"] = "pdat"

        response = self._get("esearch.fcgi", params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise PubMedError("PubMed ESearch 返回格式异常。") from exc

        error_message = _extract_esearch_errors(payload)
        if error_message:
            raise PubMedError(f"PubMed 检索式错误：{error_message}")

        try:
            result = payload["esearchresult"]
            total = int(result.get("count", 0))
            pmids = result.get("idlist") or []
        except (KeyError, TypeError, ValueError) as exc:
            raise PubMedError("PubMed ESearch 返回格式异常。") from exc
        return total, [str(pmid) for pmid in pmids]

    def _esearch_ids(self, query: str, *, db: str, retmax: int = 1) -> list[str]:
        """通用 ESearch，返回 ID 列表；无命中返回空列表。"""
        params: dict[str, Any] = {
            "db": db,
            "term": query,
            "retmax": retmax,
            "retmode": "json",
        }
        response = self._get("esearch.fcgi", params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise PubMedError("PubMed ESearch 返回格式异常。") from exc
        error_message = _extract_esearch_errors(payload)
        if error_message:
            raise PubMedError(f"PubMed 检索式错误：{error_message}")
        try:
            result = payload["esearchresult"]
            ids = result.get("idlist") or []
        except (KeyError, TypeError) as exc:
            raise PubMedError("PubMed ESearch 返回格式异常。") from exc
        return [str(item) for item in ids]

    def _efetch(self, pmids: list[str], *, batch_size: int = 200) -> list[dict]:
        """分批 EFetch，保持 PMID 顺序。"""
        if not pmids:
            return []
        by_pmid: dict[str, dict] = {}
        for start in range(0, len(pmids), batch_size):
            batch = pmids[start : start + batch_size]
            response = self._get(
                "efetch.fcgi",
                {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
            )
            for article in parse_pubmed_xml(response.text):
                by_pmid[str(article["pmid"])] = article
        return [by_pmid[pmid] for pmid in pmids if pmid in by_pmid]


def _extract_esearch_errors(payload: dict[str, Any]) -> str | None:
    """从 ESearch JSON 中提取错误信息。"""
    if "ERROR" in payload:
        return str(payload["ERROR"])

    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        return None

    errorlist = result.get("errorlist")
    if not errorlist:
        return None

    if isinstance(errorlist, dict):
        phrases = errorlist.get("phrase") or errorlist.get("field") or errorlist.get("word")
        if isinstance(phrases, list):
            return "; ".join(str(item) for item in phrases)
        if phrases:
            return str(phrases)

    return str(errorlist)


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    text = "".join(element.itertext()).strip()
    return text or None


def _find_text(root: ET.Element, path: str) -> str | None:
    return _text(root.find(path))


def _filter_entry_terms(descriptor: str, original: str, terms: list[str]) -> list[str]:
    """去掉与官方名/原文重复的入口词，并限制数量。"""
    skip = {descriptor.casefold(), original.casefold()}
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.casefold()
        if not term or key in skip or key in seen:
            continue
        seen.add(key)
        unique.append(term)
        if len(unique) >= MAX_MESH_ENTRY_TERMS:
            break
    return unique


def _normalize_mesh_key(text: str) -> str:
    """忽略大小写、空格与标点，便于比对入口词。"""
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def parse_mesh_esummary_item(item: dict[str, Any]) -> tuple[str, str, list[str]] | None:
    """从 ESummary 单条记录取出 (官方名, 字段标签, 入口词)。"""
    raw_terms = item.get("ds_meshterms") or []
    if not isinstance(raw_terms, list):
        return None
    terms = [str(term).strip() for term in raw_terms if str(term).strip()]
    if not terms:
        return None
    record_type = str(item.get("ds_recordtype") or "")
    mapped = str(item.get("ds_headingmappedto") or "").strip()
    if record_type == "supplemental-record":
        if mapped:
            return mapped, "MeSH Terms", terms
        return terms[0], "Supplementary Concept", terms[1:]
    return terms[0], "MeSH Terms", terms[1:]


def _mesh_term_score(query: str, terms: list[str], record_type: str) -> tuple[int, int]:
    """(匹配强度, 是否描述符)。强度 0 表示对不上，不得采用。"""
    query_key = _normalize_mesh_key(query)
    if not query_key:
        return (0, 0)
    term_keys = [_normalize_mesh_key(term) for term in terms if term]
    is_descriptor = 1 if record_type == "descriptor" else 0
    if any(key == query_key for key in term_keys):
        return (2, is_descriptor)
    if len(query_key) >= 4 and any(
        query_key in key or (len(key) >= 4 and key in query_key) for key in term_keys
    ):
        return (1, is_descriptor)
    return (0, 0)


def _mesh_summaries_from_payload(
    payload: dict[str, Any], ids: list[str]
) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    summaries: list[dict[str, Any]] = []
    for uid in ids:
        item = result.get(uid)
        if isinstance(item, dict):
            summaries.append(item)
    return summaries


def select_best_mesh_summary(
    query: str, summaries: list[dict[str, Any]]
) -> tuple[dict[str, Any], tuple[str, str, list[str]]] | None:
    """在候选中选与用户原文对得上的记录；对不上则返回 None，不编造。"""
    ranked: list[tuple[tuple[int, int, int], dict[str, Any], tuple[str, str, list[str]]]] = []
    for index, item in enumerate(summaries):
        parsed = parse_mesh_esummary_item(item)
        if parsed is None:
            continue
        descriptor, _tag, extra = parsed
        score = _mesh_term_score(
            query,
            [descriptor, *extra],
            str(item.get("ds_recordtype") or ""),
        )
        if score[0] <= 0:
            continue
        ranked.append(((*score, -index), item, parsed))
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0], reverse=True)
    _score, item, parsed = ranked[0]
    return item, parsed


def parse_mesh_xml(xml_text: str) -> tuple[str, str, list[str]] | None:
    """解析 MeSH EFetch XML，返回 (官方名, PubMed 字段标签, 入口词)。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PubMedError("MeSH XML 解析失败。") from exc

    descriptor_el = root.find(".//DescriptorRecord")
    if descriptor_el is not None:
        name = _find_text(descriptor_el, "DescriptorName/String") or _find_text(
            descriptor_el, ".//DescriptorName/String"
        )
        if not name:
            return None
        terms = _collect_mesh_terms(descriptor_el)
        return name, "MeSH Terms", terms

    supplemental_el = root.find(".//SupplementalRecord")
    if supplemental_el is not None:
        mapped = _find_text(
            supplemental_el,
            ".//DescriptorReferredTo/DescriptorName/String",
        )
        supp_name = _find_text(supplemental_el, "SupplementalRecordName/String") or _find_text(
            supplemental_el, ".//SupplementalRecordName/String"
        )
        terms = _collect_mesh_terms(supplemental_el)
        if mapped:
            return mapped, "MeSH Terms", terms
        if supp_name:
            return supp_name, "Supplementary Concept", terms
        return None
    return None


def _collect_mesh_terms(record: ET.Element) -> list[str]:
    """收集非倒置入口词。"""
    terms: list[str] = []
    for term_el in record.findall(".//TermList/Term"):
        if term_el.get("IsPermutedTermYN") == "Y":
            continue
        text = _find_text(term_el, "String")
        if text:
            terms.append(text)
    return terms


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    """解析 PubMed XML，返回原始字段 dict 列表。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PubMedError("PubMed XML 解析失败。") from exc

    articles: list[dict] = []
    for article_el in root.findall(".//PubmedArticle"):
        medline = article_el.find("MedlineCitation")
        if medline is None:
            continue

        pmid = _find_text(medline, "PMID")
        if not pmid:
            continue

        article = medline.find("Article")
        title = _find_text(article, "ArticleTitle") if article is not None else None

        authors: list[str] = []
        if article is not None:
            for author in article.findall(".//AuthorList/Author"):
                last_name = _find_text(author, "LastName")
                fore_name = _find_text(author, "ForeName")
                collective = _find_text(author, "CollectiveName")
                if collective:
                    authors.append(collective)
                elif last_name and fore_name:
                    authors.append(f"{last_name} {fore_name}")
                elif last_name:
                    authors.append(last_name)

        journal = None
        pub_date = None
        pub_year = None
        if article is not None:
            journal = _find_text(article, "Journal/Title")
            pub_date_el = article.find("Journal/JournalIssue/PubDate")
            if pub_date_el is not None:
                year = _find_text(pub_date_el, "Year")
                month = _find_text(pub_date_el, "Month")
                day = _find_text(pub_date_el, "Day")
                if year:
                    pub_year = int(year)
                    parts = [year]
                    if month:
                        parts.append(month)
                    if day:
                        parts.append(day)
                    pub_date = "-".join(parts)

        publication_types: list[str] = []
        if article is not None:
            for pt in article.findall("PublicationTypeList/PublicationType"):
                if pt.text:
                    publication_types.append(pt.text.strip())

        abstract = _parse_abstract(article)

        doi = None
        pubmed_data = article_el.find("PubmedData")
        if pubmed_data is not None:
            for article_id in pubmed_data.findall("ArticleIdList/ArticleId"):
                if article_id.get("IdType") == "doi" and article_id.text:
                    doi = article_id.text.strip()
                    break

        articles.append(
            {
                "pmid": pmid,
                "doi": doi,
                "title": title,
                "authors": authors,
                "journal": journal,
                "publication_date": pub_date,
                "publication_year": pub_year,
                "publication_types": publication_types,
                "abstract": abstract,
            }
        )
    return articles


def _parse_abstract(article: ET.Element | None) -> str | None:
    if article is None:
        return None
    abstract_el = article.find("Abstract")
    if abstract_el is None:
        return None

    parts: list[str] = []
    for section in abstract_el.findall("AbstractText"):
        label = section.get("Label")
        text = _text(section)
        if not text:
            continue
        if label:
            parts.append(f"{label}\n{text}")
        else:
            parts.append(text)
    if not parts:
        return _text(abstract_el)
    return "\n\n".join(parts)
