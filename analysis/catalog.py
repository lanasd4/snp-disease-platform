"""
Study-level view of the local GWAS Catalog snapshot, shared by the analyses.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from core.diseases import list_diseases
from core.paths import PROJECT_ROOT
from pipeline.extract_from_catalog import find_latest_catalog

CACHE_DIR = PROJECT_ROOT / "analysis" / "cache"
GENOME_WIDE_P = 5e-8
COLUMNS = ["STUDY ACCESSION", "PUBMEDID", "DATE", "INITIAL SAMPLE SIZE", "REPLICATION SAMPLE SIZE",
           "MAPPED_TRAIT", "P-VALUE"]


def _scan(catalog_path: Path) -> pd.DataFrame:
    trait_to_disease = {trait: d.name_en for d in list_diseases() for trait in d.gwas_traits}
    studies: dict = {}
    disease_hits: dict = {}
    sig_counts: dict = {}

    with zipfile.ZipFile(catalog_path) as archive:
        member = max(archive.infolist(), key=lambda info: info.file_size)
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", usecols=COLUMNS, dtype=str, chunksize=250_000,
                                     low_memory=False):
                chunk = chunk[COLUMNS]  # usecols keeps file order; force ours
                chunk["trait"] = chunk["MAPPED_TRAIT"].fillna("").str.strip().str.lower()
                chunk["disease"] = chunk["trait"].map(trait_to_disease)
                chunk["significant"] = pd.to_numeric(chunk["P-VALUE"], errors="coerce") < GENOME_WIDE_P

                firsts = chunk.drop_duplicates("STUDY ACCESSION")
                for row in firsts.itertuples(index=False):
                    studies.setdefault(row[0], row[:5])

                for (accession, disease), group in chunk.dropna(subset=["disease"]).groupby(
                        ["STUDY ACCESSION", "disease"]):
                    disease_hits.setdefault(accession, set()).add(disease)
                    sig_counts[(accession, disease)] = sig_counts.get((accession, disease), 0) + int(
                        group["significant"].sum())

    table = pd.DataFrame(list(studies.values()), columns=COLUMNS[:5])
    table.columns = ["accession", "pubmed_id", "date", "initial_sample", "replication_sample"]
    table["year"] = pd.to_datetime(table["date"], errors="coerce").dt.year
    table["diseases"] = table["accession"].map(lambda a: ";".join(sorted(disease_hits.get(a, []))))
    table["significant_by_disease"] = table["accession"].map(
        lambda a: ";".join(f"{d}={sig_counts[(a, d)]}" for d in sorted(disease_hits.get(a, []))))
    return table


def load_studies(catalog_path: Path | None = None, refresh: bool = False) -> pd.DataFrame:
    catalog_path = catalog_path or find_latest_catalog()
    cache = CACHE_DIR / f"studies_{catalog_path.stem}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, dtype={"accession": str, "pubmed_id": str})
    table = _scan(catalog_path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(cache, index=False)
    return table


def catalog_name(catalog_path: Path | None = None) -> str:
    return (catalog_path or find_latest_catalog()).name
