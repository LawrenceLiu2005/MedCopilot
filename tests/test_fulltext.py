"""全文拉取与 PDF 抽字测试（无真实网络）。"""

from io import BytesIO

import pytest
from pypdf import PdfWriter

from src.services.fulltext import (
    FullTextDocument,
    FullTextError,
    SOURCE_PDF_UPLOAD,
    _best_oa_pdf_url,
    _pmcid_from_elink,
    extract_text_from_pdf,
    extract_text_from_pmc_xml,
)


def _minimal_pdf_bytes(text: str) -> bytes:
    """生成含一行文字的简单 PDF（部分环境抽字可能为空，另测 XML）。"""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_text_from_pmc_xml_reads_body_and_table():
    xml = """<?xml version="1.0"?>
    <article>
      <front><article-meta>
        <title-group><article-title>Trial of Drug X</article-title></title-group>
        <abstract><p>Abstract only mentions percent.</p></abstract>
      </article-meta></front>
      <body>
        <sec><title>Results</title>
          <p>Events were 15 of 40 versus 24 of 37.</p>
          <table>
            <tr><th>Group</th><th>Events</th><th>N</th></tr>
            <tr><td>Drug</td><td>15</td><td>40</td></tr>
            <tr><td>Control</td><td>24</td><td>37</td></tr>
          </table>
        </sec>
      </body>
    </article>
    """
    text = extract_text_from_pmc_xml(xml)
    assert "Trial of Drug X" in text
    assert "15 of 40" in text
    assert "表格" in text
    assert "15 | 40" in text or "15" in text


def test_pmcid_from_elink_payload():
    payload = {
        "linksets": [
            {
                "linksetdbs": [
                    {"dbto": "pmc", "linkname": "pubmed_pmc", "links": ["1234567"]},
                ]
            }
        ]
    }
    assert _pmcid_from_elink(payload) == "PMC1234567"
    assert _pmcid_from_elink({"linksets": []}) is None


def test_pmcid_ignores_pmc_refs_only():
    """只有被引用链接时，不能当成本文有 PMC 全文。"""
    payload = {
        "linksets": [
            {
                "linksetdbs": [
                    {"dbto": "pmc", "linkname": "pubmed_pmc_refs", "links": ["9145954"]},
                ]
            }
        ]
    }
    assert _pmcid_from_elink(payload) is None


def test_pmcid_prefers_pubmed_pmc_over_refs():
    payload = {
        "linksets": [
            {
                "linksetdbs": [
                    {"dbto": "pmc", "linkname": "pubmed_pmc_refs", "links": ["999"]},
                    {"dbto": "pmc", "linkname": "pubmed_pmc", "links": ["7809486"]},
                ]
            }
        ]
    }
    assert _pmcid_from_elink(payload) == "PMC7809486"


def test_best_oa_pdf_url_prefers_url_for_pdf():
    payload = {
        "best_oa_location": {
            "url": "https://example.com/landing",
            "url_for_pdf": "https://example.com/paper.pdf",
        }
    }
    assert _best_oa_pdf_url(payload) == "https://example.com/paper.pdf"


def test_empty_pdf_raises():
    with pytest.raises(FullTextError, match="为空"):
        extract_text_from_pdf(b"", pmid="1")


def test_blank_pdf_raises_when_no_text():
    data = _minimal_pdf_bytes("ignored")
    with pytest.raises(FullTextError, match="抽不出文字"):
        extract_text_from_pdf(data, pmid="1")


def test_fulltext_document_truncates():
    doc = FullTextDocument(
        pmid="1",
        source=SOURCE_PDF_UPLOAD,
        text="字" * 100,
        notes="上传",
    )
    assert doc.char_count == 100
    short = doc.truncated_for_model(limit=10)
    assert short.startswith("字" * 10)
    assert "截断" in short
