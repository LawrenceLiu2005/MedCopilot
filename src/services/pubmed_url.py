"""解析 PubMed 网页链接参数（不抓取网页）。"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from src.services.search import ALLOWED_RETMAX, MAX_RETMAX

PUBMED_HOSTS = {"pubmed.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}


@dataclass
class PubMedUrlImport:
    """从 PubMed 网页 URL 提取的检索条件。"""

    term: str
    sort: str | None
    size_hint: int | None


def parse_pubmed_url(url: str) -> PubMedUrlImport | None:
    """解析 PubMed 搜索页 URL；无法识别时返回 None。"""
    text = url.strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.netloc not in PUBMED_HOSTS:
        return None

    params = parse_qs(parsed.query)
    terms = params.get("term") or params.get("query")
    if not terms or not terms[0].strip():
        return None

    sort_values = params.get("sort")
    sort = sort_values[0].strip() if sort_values and sort_values[0].strip() else None

    size_hint = None
    size_values = params.get("size")
    if size_values:
        try:
            size_hint = int(size_values[0])
        except (ValueError, TypeError):
            size_hint = None

    return PubMedUrlImport(term=terms[0].strip(), sort=sort, size_hint=size_hint)


def map_sort_to_api(web_sort: str | None) -> str | None:
    """网页 sort 参数 → ESearch sort。"""
    if web_sort == "date":
        return "pub_date"
    return None


def suggest_retmax(size_hint: int | None) -> int:
    """根据网页 size 建议返回条数，不超过项目上限。"""
    if size_hint is None:
        return ALLOWED_RETMAX[0]
    capped = min(max(size_hint, 1), MAX_RETMAX)
    for option in reversed(ALLOWED_RETMAX):
        if capped >= option:
            return option
    return ALLOWED_RETMAX[0]
