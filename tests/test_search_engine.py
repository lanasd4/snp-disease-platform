"""
Behaviour of the tri-search engine (disease / SNP / gene) used by the Search page.
"""

import pytest

from core.search_engine import is_rsid_query, normalize_text, search_tri_ranked_file


def search(query, mode, arab_only=False, limit=50):
    return search_tri_ranked_file(query=query, search_mode=mode, arab_related_only=arab_only, limit=limit)


@pytest.mark.parametrize("query", ["Type 2 Diabetes", "type 2 diabetes", "السكري", "Obesity", "السمنة", "Asthma"])
def test_disease_search_finds_results(query):
    result = search(query, "disease")
    assert result["found"] is True
    assert result["result_count"] > 0
    assert len(result["results"]) == result["result_count"]


def test_snp_search_finds_known_variant():
    result = search("rs7903146", "snp")
    assert result["found"] is True
    assert all(str(row["rsid"]).lower() == "rs7903146" for row in result["results"])


def test_gene_search_finds_known_gene():
    result = search("TCF7L2", "gene")
    assert result["found"] is True
    assert any("TCF7L2" in str(row.get("gene_symbol", "")) for row in result["results"])


def test_limit_is_respected():
    assert search("Type 2 Diabetes", "disease", limit=5)["result_count"] <= 5


@pytest.mark.parametrize("query", ["zzzzqqq", "rs000000000", ""])
def test_unknown_or_empty_query_returns_no_results_without_error(query):
    result = search(query, "disease")
    assert result["found"] is False
    assert result["result_count"] == 0


@pytest.mark.parametrize("query", ["<script>alert(1)</script>", "' OR 1=1 --", "../../etc/passwd", "a" * 5000])
def test_hostile_input_is_handled(query):
    for mode in ("disease", "snp", "gene"):
        result = search(query, mode)
        assert isinstance(result, dict)
        assert result["result_count"] == 0


def test_rsid_detection():
    assert is_rsid_query("rs7903146")
    assert is_rsid_query("RS7903146")
    assert not is_rsid_query("TCF7L2")


def test_arabic_normalization_unifies_letter_forms():
    assert normalize_text("السمنة") == normalize_text("السمنه")
    assert normalize_text("أ") == normalize_text("ا")
