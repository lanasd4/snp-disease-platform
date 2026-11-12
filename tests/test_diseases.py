"""
Disease registry (core.diseases) and the rebuilt 10-disease dataset.
"""

import sqlite3

import pandas as pd
import pytest

from core.diseases import get_disease, list_diseases, resolve_disease
from core.paths import RANKED_ASSOCIATIONS_FILE
from core.search_engine import search_tri_ranked_file
from tests.conftest import PROJECT_ROOT

EXPECTED = [
    "Type 2 Diabetes", "Obesity", "Hypertension", "Coronary Artery Disease", "Chronic Kidney Disease",
    "Asthma", "Hypothyroidism", "Rheumatoid Arthritis", "Alzheimer's Disease", "Breast Cancer",
]


def test_registry_lists_the_ten_diseases_in_order():
    assert [d.name_en for d in list_diseases()] == EXPECTED


def test_every_disease_has_arabic_name_icon_description_and_gwas_traits():
    for d in list_diseases():
        assert d.name_ar and d.icon and d.description_ar and d.description_en and d.gwas_traits, d.name_en


@pytest.mark.parametrize("query, expected", [
    ("السكري", "Type 2 Diabetes"), ("سكري", "Type 2 Diabetes"), ("T2D", "Type 2 Diabetes"),
    ("السمنه", "Obesity"), ("بدانة", "Obesity"), ("الضغط", "Hypertension"),
    ("CAD", "Coronary Artery Disease"), ("الفشل الكلوي", "Chronic Kidney Disease"), ("ربو", "Asthma"),
    ("قصور الغدة الدرقية", "Hypothyroidism"), ("خمول الغدة الدرقية", "Hypothyroidism"),
    ("الروماتيزم", "Rheumatoid Arthritis"), ("RA", "Rheumatoid Arthritis"),
    ("الزهايمر", "Alzheimer's Disease"), ("زهايمر", "Alzheimer's Disease"), ("alzheimer", "Alzheimer's Disease"),
    ("سرطان الثدي", "Breast Cancer"), ("breast carcinoma", "Breast Cancer"),
])
def test_synonyms_resolve(query, expected):
    assert resolve_disease(query).name_en == expected


@pytest.mark.parametrize("query", ["", "   ", "xyz", "cancer", "<b>x</b>"])
def test_unknown_terms_do_not_resolve(query):
    assert resolve_disease(query) is None


def test_get_disease_by_id_and_name():
    assert get_disease(9).name_en == "Alzheimer's Disease"
    assert get_disease("Breast Cancer").disease_id == 10


@pytest.mark.parametrize("name", EXPECTED)
def test_every_disease_is_searchable(name):
    disease = get_disease(name)
    for query in (disease.name_en, disease.name_ar):
        result = search_tri_ranked_file(query=query, search_mode="disease", limit=500)
        assert result["result_count"] > 0, query
        assert {row["disease_name"] for row in result["results"]} == {name}


def test_ranked_file_is_balanced_across_diseases():
    ranked = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    snps_per_disease = ranked.groupby("disease_name")["rsid"].nunique()
    assert set(snps_per_disease.index) == set(EXPECTED)
    assert snps_per_disease.max() <= 150
    assert snps_per_disease.min() >= 50


def test_published_database_has_no_demo_rows_and_all_diseases():
    with sqlite3.connect(PROJECT_ROOT / "database" / "snp_platform.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM Study WHERE source_name = 'Demo Source'").fetchone()[0] == 0
        names = {r[0] for r in conn.execute(
            "SELECT DISTINCT d.canonical_name FROM Association a JOIN Disease d USING (disease_id)")}
    assert names == set(EXPECTED)


def test_known_biology_sanity_checks():
    """Well-established associations must be present (guards against a broken rebuild)."""
    ranked = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    pairs = set(zip(ranked["disease_name"], ranked["gene_symbol"]))
    assert ("Alzheimer's Disease", "APOE") in pairs
    assert ("Type 2 Diabetes", "TCF7L2") in pairs


def test_ranked_rows_keep_study_metadata():
    """PubMed id, journal and OR/beta must survive the pipeline (they were silently dropped before)."""
    ranked = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    assert ranked["pubmed_id"].notna().mean() > 0.95
    assert ranked["journal"].notna().mean() > 0.95
    assert ranked["odds_ratio"].notna().mean() > 0.5


def test_population_is_ancestry_not_chromosome_band():
    """population_label comes from the sample description, never a cytoband like 7p15.1."""
    ranked = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    assert not ranked["population_label"].str.fullmatch(r"\d{1,2}[pq][\d.]+", na=False).any()
    assert ranked["population_label"].str.contains("European", na=False).any()
    assert (ranked["is_arab_related_flag"] == "1").sum() > 100
