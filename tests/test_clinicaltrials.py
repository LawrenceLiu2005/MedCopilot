"""ClinicalTrials.gov 客户端测试。"""

from unittest.mock import MagicMock

import pytest

from src.clients.clinicaltrials import (
    ClinicalTrialsClient,
    ClinicalTrialsError,
    build_ctgov_query,
    hit_from_dict,
)


def test_build_ctgov_query_from_pico():
    query = build_ctgov_query(
        population="type 2 diabetes",
        intervention="metformin",
        research_question="ignored",
    )
    assert "type 2 diabetes" in query
    assert "metformin" in query
    assert "AND" in query
    assert "ignored" not in query


def test_build_ctgov_query_falls_back_to_research_question():
    query = build_ctgov_query(research_question="二甲双胍 糖尿病")
    assert query == "二甲双胍 糖尿病"


def test_search_parses_studies(monkeypatch):
    payload = {
        "totalCount": 2,
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT00000001",
                        "briefTitle": "Metformin trial",
                    },
                    "statusModule": {"overallStatus": "COMPLETED"},
                }
            },
            {"protocolSection": {"identificationModule": {}}},
        ],
    }

    def fake_get(url, params=None, timeout=None, headers=None):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        return response

    monkeypatch.setattr("src.clients.clinicaltrials.httpx.get", fake_get)
    total, hits = ClinicalTrialsClient().search("metformin")
    assert total == 2
    assert len(hits) == 1
    assert hits[0].nct_id == "NCT00000001"
    assert hits[0].status == "COMPLETED"
    assert hits[0].url.endswith("NCT00000001")


def test_search_http_error(monkeypatch):
    def fake_get(url, params=None, timeout=None, headers=None):
        response = MagicMock()
        response.status_code = 502
        return response

    monkeypatch.setattr("src.clients.clinicaltrials.httpx.get", fake_get)
    with pytest.raises(ClinicalTrialsError, match="服务器错误"):
        ClinicalTrialsClient().search("metformin")


def test_hit_from_dict_roundtrip():
    hit = hit_from_dict(
        {
            "nct_id": "NCT1",
            "title": "T",
            "status": "RECRUITING",
            "url": "https://clinicaltrials.gov/study/NCT1",
        }
    )
    assert hit.nct_id == "NCT1"
    assert hit.status == "RECRUITING"
