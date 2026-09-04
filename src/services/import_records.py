"""RIS / NBIB / PMID 列表导入。"""

from __future__ import annotations

import re
from io import StringIO

import nbib
import rispy

from src.models.evidence import EvidenceRecord

PMID_PATTERN = re.compile(r"^\d+$")


def parse_pmid_list(text: str) -> list[str]:
    """从逗号、空格或换行分隔的文本中提取 PMID。"""
    tokens = re.split(r"[\s,;]+", text.strip())
    seen: set[str] = set()
    pmids: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        if cleaned and PMID_PATTERN.match(cleaned) and cleaned not in seen:
            seen.add(cleaned)
            pmids.append(cleaned)
    return pmids


def _year_from_ris(entry: dict) -> int | None:
    year = entry.get("year") or entry.get("publication_year")
    if year is None:
        return None
    try:
        return int(str(year)[:4])
    except (TypeError, ValueError):
        return None


def _authors_from_ris(entry: dict) -> list[str]:
    authors = entry.get("authors") or entry.get("first_authors") or []
    return [str(author).strip() for author in authors if str(author).strip()]


def record_from_ris_entry(entry: dict) -> EvidenceRecord | None:
    """将单条 RIS 记录转为 EvidenceRecord；缺少 PMID 时返回 None。"""
    pmid = entry.get("accession_number") or entry.get("pmid") or entry.get("an")
    if pmid is None:
        return None
    pmid_str = str(pmid).strip()
    if not PMID_PATTERN.match(pmid_str):
        return None
    doi = entry.get("doi")
    if isinstance(doi, list):
        doi = doi[0] if doi else None
    return EvidenceRecord(
        pmid=pmid_str,
        doi=str(doi).strip() if doi else None,
        title=str(entry.get("title") or "").strip(),
        authors=_authors_from_ris(entry),
        journal=(str(entry.get("journal_name") or entry.get("secondary_title") or "").strip() or None),
        publication_date=str(entry.get("date") or "").strip() or None,
        publication_year=_year_from_ris(entry),
        publication_types=[str(entry.get("type_of_reference") or "JOUR")],
        abstract=str(entry.get("abstract") or "").strip() or None,
        source="ris_import",
    )


def parse_ris_text(text: str) -> tuple[list[EvidenceRecord], list[str]]:
    """解析 RIS 文本，返回 (有 PMID 的记录, 缺少 PMID 的标题列表)。"""
    entries = rispy.loads(text)
    records: list[EvidenceRecord] = []
    missing_titles: list[str] = []
    for entry in entries:
        record = record_from_ris_entry(entry)
        if record is None:
            title = str(entry.get("title") or "（无标题）").strip()
            missing_titles.append(title)
            continue
        records.append(record)
    return records, missing_titles


def _year_from_nbib(entry: dict) -> int | None:
    pub_date = entry.get("publication_date")
    if not pub_date:
        return None
    match = re.match(r"(\d{4})", str(pub_date))
    if not match:
        return None
    return int(match.group(1))


def record_from_nbib_entry(entry: dict) -> EvidenceRecord | None:
    """将单条 NBIB 记录转为 EvidenceRecord。"""
    pmid = entry.get("pubmed_id")
    if pmid is None:
        return None
    pmid_str = str(pmid).strip()
    authors = [str(author).strip() for author in entry.get("authors") or [] if str(author).strip()]
    return EvidenceRecord(
        pmid=pmid_str,
        title=str(entry.get("title") or "").strip(),
        authors=authors,
        journal=str(entry.get("journal") or "").strip() or None,
        publication_date=str(entry.get("publication_date") or "").strip() or None,
        publication_year=_year_from_nbib(entry),
        abstract=str(entry.get("abstract") or "").strip() or None,
        source="nbib_import",
    )


def parse_nbib_text(text: str) -> tuple[list[EvidenceRecord], list[str]]:
    """解析 PubMed NBIB 文本。"""
    entries = nbib.read(text)
    records: list[EvidenceRecord] = []
    missing_titles: list[str] = []
    for entry in entries:
        record = record_from_nbib_entry(entry)
        if record is None:
            missing_titles.append(str(entry.get("title") or "（无标题）"))
            continue
        records.append(record)
    return records, missing_titles


def parse_ris_file_bytes(data: bytes) -> tuple[list[EvidenceRecord], list[str]]:
    """从上传文件字节解析 RIS。"""
    text = data.decode("utf-8", errors="replace")
    return parse_ris_text(text)


def parse_nbib_file_bytes(data: bytes) -> tuple[list[EvidenceRecord], list[str]]:
    """从上传文件字节解析 NBIB。"""
    text = data.decode("utf-8", errors="replace")
    return parse_nbib_text(text)
