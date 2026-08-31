"""PubMed 客户端测试。"""

import os
from unittest.mock import MagicMock

import pytest

from src.clients.pubmed import PubMedClient, PubMedConfigError, PubMedError, parse_pubmed_xml
from src.config.ncbi_credentials import has_ncbi_email
from src.models.evidence import EvidenceRecord, ScreeningStatus

SAMPLE_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE">
      <PMID Version="1">12345678</PMID>
      <Article>
        <ArticleTitle>Sample Diabetes Study</ArticleTitle>
        <AuthorList>
          <Author>
            <LastName>Zhang</LastName>
            <ForeName>Wei</ForeName>
          </Author>
        </AuthorList>
        <Journal>
          <Title>Test Journal</Title>
          <JournalIssue>
            <PubDate>
              <Year>2024</Year>
              <Month>Jan</Month>
              <Day>15</Day>
            </PubDate>
          </JournalIssue>
        </Journal>
        <Abstract>
          <AbstractText Label="BACKGROUND">Background text.</AbstractText>
          <AbstractText Label="METHODS">Methods text.</AbstractText>
        </Abstract>
        <PublicationTypeList>
          <PublicationType>Journal Article</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1000/test.doi</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_parse_pubmed_xml_to_evidence_record():
    articles = parse_pubmed_xml(SAMPLE_XML)
    assert len(articles) == 1
    record = EvidenceRecord.from_pubmed_dict(articles[0])
    assert record.pmid == "12345678"
    assert record.title == "Sample Diabetes Study"
    assert record.authors == ["Zhang Wei"]
    assert record.journal == "Test Journal"
    assert record.publication_year == 2024
    assert record.publication_date == "2024-Jan-15"
    assert record.doi == "10.1000/test.doi"
    assert record.publication_types == ["Journal Article"]
    assert "BACKGROUND\nBackground text." in (record.abstract or "")
    assert "METHODS\nMethods text." in (record.abstract or "")
    assert record.screening_status == ScreeningStatus.UNSCREENED


def test_missing_ncbi_email_raises(monkeypatch):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.setattr(
        "src.clients.pubmed.resolve_ncbi_email",
        lambda **kwargs: None,
    )
    with pytest.raises(PubMedConfigError, match="NCBI 邮箱"):
        PubMedClient(email="")


def test_efetch_batches_and_preserves_order(monkeypatch):
    """EFetch 分批请求并保持 PMID 顺序。"""
    client = PubMedClient(email="test@example.com")
    call_batches: list[list[str]] = []

    def fake_get(_self, endpoint, params):
        assert endpoint == "efetch.fcgi"
        ids = params["id"].split(",")
        call_batches.append(ids)
        xml_parts = []
        for pmid in ids:
            xml_parts.append(
                f"""<PubmedArticle>
    <MedlineCitation><PMID>{pmid}</PMID>
      <Article><ArticleTitle>Title {pmid}</ArticleTitle></Article>
    </MedlineCitation></PubmedArticle>"""
            )
        from unittest.mock import MagicMock

        response = MagicMock()
        response.status_code = 200
        response.text = f'<?xml version="1.0"?><PubmedArticleSet>{"".join(xml_parts)}</PubmedArticleSet>'
        return response

    monkeypatch.setattr(PubMedClient, "_get", fake_get)
    pmids = [str(i) for i in range(250)]
    articles = client._efetch(pmids, batch_size=200)
    assert len(call_batches) == 2
    assert len(call_batches[0]) == 200
    assert len(call_batches[1]) == 50
    assert [a["pmid"] for a in articles] == pmids


@pytest.mark.skipif(not has_ncbi_email(), reason="需要 NCBI 邮箱（设置页、.env 或 workspace.json）")
def test_live_pubmed_search():
    client = PubMedClient()
    total, records, missing_pmids = client.search('"diabetes"[Title]', retmax=2)
    assert total > 0
    assert len(records) >= 1
    assert records[0].pmid
    assert records[0].title
    assert missing_pmids == []


def test_esearch_errorlist_raises_pubmed_error(monkeypatch):
    client = PubMedClient(email="test@example.com")

    def fake_get(_self, endpoint, params):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "esearchresult": {
                "count": "0",
                "idlist": [],
                "errorlist": {"phrase": ["Invalid query syntax"]},
            }
        }
        return response

    monkeypatch.setattr(PubMedClient, "_get", fake_get)
    with pytest.raises(PubMedError, match="检索式错误"):
        client._esearch("bad[[query", retmax=10, mindate=None, maxdate=None)


def test_search_reports_missing_pmids(monkeypatch):
    client = PubMedClient(email="test@example.com")

    def fake_esearch(_self, query, *, retmax, mindate, maxdate, sort=None):
        return 3, ["1", "2", "3"]

    def fake_efetch(_self, pmids, *, batch_size=200):
        return [{"pmid": "1", "title": "A", "authors": [], "publication_types": []}]

    monkeypatch.setattr(PubMedClient, "_esearch", fake_esearch)
    monkeypatch.setattr(PubMedClient, "_efetch", fake_efetch)

    total, records, missing_pmids = client.search("test", retmax=3)
    assert total == 3
    assert len(records) == 1
    assert missing_pmids == ["2", "3"]
