"""
Admin data workflow end to end (upload -> validate -> approve -> merge -> rollback)
on a throwaway copy of the ranked file and the source registry.
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest

import core.admin.common as common
from core.admin import approval_merge as am
from core.admin import data_ingestion as di
from core.admin import final_merge as fm
from core.paths import DATA_SOURCES_REGISTRY_FILE, RANKED_ASSOCIATIONS_FILE


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "data/metadata").mkdir(parents=True)
    (tmp_path / "data/raw/admin_uploaded").mkdir(parents=True)
    ranked = tmp_path / "data/processed/ranked_associations_initial.csv"
    registry = tmp_path / "data/metadata/data_sources_registry.csv"
    shutil.copy(RANKED_ASSOCIATIONS_FILE, ranked)
    shutil.copy(DATA_SOURCES_REGISTRY_FILE, registry)
    monkeypatch.setattr(common, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(common, "RANKED_ASSOCIATIONS_FILE", ranked)
    monkeypatch.setattr(common, "DATA_SOURCES_REGISTRY_FILE", registry)
    monkeypatch.setattr(common, "OUTPUT_TABLES_DIR", tmp_path / "outputs/tables")
    for module in (di, am, fm):
        monkeypatch.setattr(module, "get_project_root", lambda: tmp_path)
    return tmp_path


def _ranked(root: Path) -> pd.DataFrame:
    return pd.read_csv(root / "data/processed/ranked_associations_initial.csv", dtype=str, keep_default_na=False)


def _upload(root: Path, name: str, rows: list, sep: str = ",") -> dict:
    path = root / "data/raw/admin_uploaded" / name
    pd.DataFrame(rows).to_csv(path, index=False, sep=sep)
    return di.run_uploaded_source_pipeline(path, source_name=name)


def test_rows_are_validated_and_normalized(root):
    result = _upload(root, "a.csv", [
        {"SNP": "rs99990001", "Trait": "type 2 diabetes mellitus", "Gene": "G1", "P-value": "3e-12", "PMID": "123"},
        {"SNP": "rs99990001", "Trait": "السكري", "Gene": "G1", "P-value": "1e-9"},  # duplicate, weaker p
        {"SNP": "bad", "Trait": "Asthma", "Gene": "X", "P-value": "1e-8"},
        {"SNP": "rs1", "Trait": "Asthma", "Gene": "X", "P-value": "7"},
        {"SNP": "rs2", "Trait": "Height", "Gene": "X", "P-value": "1e-9"},
    ])
    assert (result["accepted_rows"], result["rejected_rows"]) == (1, 3)
    processed = pd.read_csv(root / result["processed_path"], dtype=str, keep_default_na=False)
    assert processed.iloc[0]["disease_name"] == "Type 2 Diabetes"
    assert float(processed.iloc[0]["p_value"]) == 3e-12
    assert processed.iloc[0]["pubmed_id"] == "123"
    rejected = pd.read_csv(root / result["rejected_rows_path"], dtype=str, keep_default_na=False)
    assert set(rejected["rejection_reason"]) == {"invalid_or_missing_rsid", "p_value_out_of_range",
                                                 "disease_not_on_platform"}


def test_minus_log10_p_column_is_converted(root):
    result = _upload(root, "b.tsv", [{"rsid": "rs99980001", "disease": "Asthma", "gene": "B1", "PVALUE_MLOG": "15"}],
                     sep="\t")
    processed = pd.read_csv(root / result["processed_path"])
    assert processed.iloc[0]["p_value"] == pytest.approx(1e-15)


def test_file_without_required_columns_is_not_processed(root):
    result = _upload(root, "c.csv", [{"foo": 1}])
    assert result["status"] == "validation_failed"


def test_merge_two_sources_and_roll_back_one(root):
    base = _ranked(root)
    a = _upload(root, "a.csv", [{"rsid": "rs99990001", "disease": "Type 2 Diabetes", "gene": "G1",
                                 "p_value": "3e-12", "ancestry": "Saudi Arab ancestry", "risk allele": "rs99990001-T"}])
    b = _upload(root, "b.csv", [{"rsid": "rs99980001", "disease": "Asthma", "gene": "B1", "p_value": "1e-15"}])
    am.approve_source(a["source_id"], "admin")
    am.approve_source(b["source_id"], "admin")  # approved before A is merged
    fm.final_merge_source(a["source_id"], "admin")
    fm.final_merge_source(b["source_id"], "admin")

    merged = _ranked(root)
    assert len(merged) == len(base) + 2
    row = merged[merged.rsid == "rs99990001"].iloc[0]
    assert (row.disease_id, row.disease_name) == ("1", "Type 2 Diabetes")
    assert row.disease_arabic_name == base[base.disease_id == "1"].disease_arabic_name.iloc[0]
    assert row.risk_allele == "T" and row.is_arab_related == "Yes"
    assert row.rank_label == "Strong" and row.evidence_tier == "2"  # one study, p < 5e-8

    with pytest.raises(ValueError):
        fm.final_merge_source(a["source_id"], "admin")  # already live

    fm.rollback_source(a["source_id"], "admin")
    after = _ranked(root)
    assert set(after.loc[after.admin_upload_source_id != "", "admin_upload_source_id"]) == {b["source_id"]}

    fm.rollback_source(b["source_id"], "admin")
    restored = _ranked(root)
    cols = ["disease_id", "rsid", "p_value", "evidence_tier"]
    as_set = lambda df: {(r[0], r[1], float(r[2]), int(float(r[3]))) for r in df[cols].values.tolist()}  # noqa: E731
    assert as_set(restored) == as_set(base)


def test_base_dataset_cannot_be_rolled_back(root):
    assert "SRC_GWAS" not in set(fm.list_merged_sources()["source_id"])
    with pytest.raises(ValueError):
        fm.rollback_source("SRC_GWAS", "admin")


def test_evidence_levels_are_stable():
    """Re-assigning levels to the published file changes nothing."""
    from core.admin.ranked_rows import rerank

    base = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str, keep_default_na=False)
    again = rerank(base)
    cols = ["ranked_association_id", "disease_id", "rsid", "evidence_tier", "rank_position_within_disease"]
    assert again[cols].astype(str).values.tolist() == base[cols].astype(str).values.tolist()


def test_new_study_can_upgrade_a_variant(root):
    """A Strong variant becomes Confirmed when an independent study replicates it."""
    base = _ranked(root)
    strong = base[(base.evidence_tier == "2") & (base.disease_id == "6")].iloc[0]
    result = _upload(root, "rep.csv", [{"rsid": strong.rsid, "disease": "Asthma", "gene": strong.gene_symbol,
                                        "p_value": "1e-10", "pmid": "99999991"}])
    am.approve_source(result["source_id"], "admin")
    fm.final_merge_source(result["source_id"], "admin")
    after = _ranked(root)
    rows = after[(after.rsid == strong.rsid) & (after.disease_id == "6")]
    assert set(rows.rank_label) == {"Confirmed"}
