"""MeSH 词表解析与 lookup_mesh 模拟测试。"""

from unittest.mock import MagicMock

from src.clients.pubmed import (
    MeshLookupResult,
    PubMedClient,
    parse_mesh_esummary_item,
    parse_mesh_xml,
    select_best_mesh_summary,
)

DESCRIPTOR_XML = """<?xml version="1.0"?>
<DescriptorRecordSet>
  <DescriptorRecord>
    <DescriptorUI>D003924</DescriptorUI>
    <DescriptorName><String>Diabetes Mellitus, Type 2</String></DescriptorName>
    <ConceptList>
      <Concept PreferredConceptYN="Y">
        <TermList>
          <Term IsPermutedTermYN="N"><String>Diabetes Mellitus, Type 2</String></Term>
          <Term IsPermutedTermYN="N"><String>Type 2 Diabetes</String></Term>
          <Term IsPermutedTermYN="Y"><String>2 Diabetes Mellitus, Type</String></Term>
        </TermList>
      </Concept>
    </ConceptList>
  </DescriptorRecord>
</DescriptorRecordSet>
"""

SUPPLEMENTAL_XML = """<?xml version="1.0"?>
<SupplementalRecordSet>
  <SupplementalRecord>
    <SupplementalRecordName><String>metformin</String></SupplementalRecordName>
    <HeadingMappedToList>
      <HeadingMappedTo>
        <DescriptorReferredTo>
          <DescriptorName><String>Metformin</String></DescriptorName>
        </DescriptorReferredTo>
      </HeadingMappedTo>
    </HeadingMappedToList>
    <ConceptList>
      <Concept>
        <TermList>
          <Term IsPermutedTermYN="N"><String>metformin</String></Term>
          <Term IsPermutedTermYN="N"><String>dimethylbiguanide</String></Term>
        </TermList>
      </Concept>
    </ConceptList>
  </SupplementalRecord>
</SupplementalRecordSet>
"""

PHENFORMIN_SUMMARY = {
    "uid": "68010629",
    "ds_meshui": "D010629",
    "ds_recordtype": "descriptor",
    "ds_meshterms": ["Phenformin", "Fenformin", "Phenylethylbiguanide"],
    "ds_headingmappedto": "",
}

METFORMIN_SUMMARY = {
    "uid": "68008687",
    "ds_meshui": "D008687",
    "ds_recordtype": "descriptor",
    "ds_meshterms": ["Metformin", "dimethylbiguanide"],
    "ds_headingmappedto": "",
}

TYPE2_SUMMARY = {
    "uid": "68003924",
    "ds_meshui": "D003924",
    "ds_recordtype": "descriptor",
    "ds_meshterms": [
        "Diabetes Mellitus, Type 2",
        "NIDDM",
        "Type 2 Diabetes",
        "Type 2 Diabetes Mellitus",
    ],
    "ds_headingmappedto": "",
}


def test_parse_mesh_descriptor_skips_permuted_terms():
    name, tag, terms = parse_mesh_xml(DESCRIPTOR_XML)
    assert name == "Diabetes Mellitus, Type 2"
    assert tag == "MeSH Terms"
    assert "Type 2 Diabetes" in terms
    assert "2 Diabetes Mellitus, Type" not in terms


def test_parse_mesh_supplemental_uses_mapped_descriptor():
    name, tag, terms = parse_mesh_xml(SUPPLEMENTAL_XML)
    assert name == "Metformin"
    assert tag == "MeSH Terms"
    assert "dimethylbiguanide" in terms


def test_parse_mesh_esummary_descriptor():
    name, tag, terms = parse_mesh_esummary_item(TYPE2_SUMMARY)
    assert name == "Diabetes Mellitus, Type 2"
    assert tag == "MeSH Terms"
    assert "Type 2 Diabetes" in terms
    assert name not in terms


def test_select_best_prefers_exact_term_not_first_hit():
    chosen = select_best_mesh_summary(
        "metformin",
        [PHENFORMIN_SUMMARY, METFORMIN_SUMMARY],
    )
    assert chosen is not None
    item, parsed = chosen
    assert item["ds_meshui"] == "D008687"
    assert parsed[0] == "Metformin"


def test_select_best_matches_entry_term_phrase():
    chosen = select_best_mesh_summary("type 2 diabetes", [TYPE2_SUMMARY])
    assert chosen is not None
    assert chosen[1][0] == "Diabetes Mellitus, Type 2"


def test_select_best_unmatched_when_only_related_hit():
    assert select_best_mesh_summary("metformin", [PHENFORMIN_SUMMARY]) is None


def test_lookup_mesh_unmatched_on_empty_idlist(monkeypatch):
    client = PubMedClient(email="test@example.com")
    monkeypatch.setattr(
        PubMedClient,
        "_esearch_ids",
        lambda self, query, *, db, retmax=1: [],
    )
    result = client.lookup_mesh("not-a-real-mesh-term-xyz")
    assert result == MeshLookupResult(query="not-a-real-mesh-term-xyz", matched=False)


def test_lookup_mesh_parses_esummary(monkeypatch):
    client = PubMedClient(email="test@example.com")
    monkeypatch.setattr(
        PubMedClient,
        "_esearch_ids",
        lambda self, query, *, db, retmax=1: ["68003924"],
    )

    def fake_get(_self, endpoint, params):
        assert endpoint == "esummary.fcgi"
        assert params["db"] == "mesh"
        assert params["retmode"] == "json"
        response = MagicMock()
        response.json.return_value = {
            "result": {"uids": ["68003924"], "68003924": TYPE2_SUMMARY},
        }
        return response

    monkeypatch.setattr(PubMedClient, "_get", fake_get)
    result = client.lookup_mesh("type 2 diabetes")
    assert result.matched is True
    assert result.descriptor == "Diabetes Mellitus, Type 2"
    assert result.mesh_id == "D003924"
    assert "NIDDM" in result.entry_terms
    assert "Type 2 Diabetes Mellitus" in result.entry_terms
    assert "Diabetes Mellitus, Type 2" not in result.entry_terms
    # 与用户原文同义的入口词不再重复列入
    assert "Type 2 Diabetes" not in result.entry_terms


def test_lookup_mesh_skips_unrelated_first_hit(monkeypatch):
    client = PubMedClient(email="test@example.com")
    monkeypatch.setattr(
        PubMedClient,
        "_esearch_ids",
        lambda self, query, *, db, retmax=1: ["68010629", "68008687"],
    )

    def fake_get(_self, endpoint, params):
        response = MagicMock()
        response.json.return_value = {
            "result": {
                "uids": ["68010629", "68008687"],
                "68010629": PHENFORMIN_SUMMARY,
                "68008687": METFORMIN_SUMMARY,
            },
        }
        return response

    monkeypatch.setattr(PubMedClient, "_get", fake_get)
    result = client.lookup_mesh("metformin")
    assert result.matched is True
    assert result.descriptor == "Metformin"


def test_lookup_mesh_unmatched_on_broken_json(monkeypatch):
    client = PubMedClient(email="test@example.com")
    monkeypatch.setattr(
        PubMedClient,
        "_esearch_ids",
        lambda self, query, *, db, retmax=1: ["1"],
    )

    def fake_get(_self, endpoint, params):
        response = MagicMock()
        response.json.side_effect = ValueError("not json")
        return response

    monkeypatch.setattr(PubMedClient, "_get", fake_get)
    result = client.lookup_mesh("metformin")
    assert result.matched is False
    assert result.descriptor is None
