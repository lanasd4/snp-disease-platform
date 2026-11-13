"""
Per disease-variant evidence from the whole GWAS Catalog snapshot.

The platform keeps at most a few rows per variant, so replication is counted
here, over every catalog row for the disease: the number of independent
publications reporting the association at genome-wide significance, the best
p-value, and the largest discovery sample.

Run:  python -m pipeline.evidence_summary [--catalog path/to/snapshot.zip]
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import pandas as pd

from core.diseases import list_diseases
from core.paths import PROCESSED_DATA_DIR, RAW_DATA_DIR
from core.regions import parse_sample_groups
from pipeline.extract_from_catalog import CATALOG_DIR, CHUNK_ROWS, GENOME_WIDE_P, METADATA_FILE, RSID_PATTERN

OUTPUT_FILE = PROCESSED_DATA_DIR / "evidence_summary.csv"
COLUMNS = ["MAPPED_TRAIT", "SNPS", "P-VALUE", "PUBMEDID", "INITIAL SAMPLE SIZE"]


def catalog_used_for_dataset() -> Path:
    """The snapshot the current dataset was extracted from (so counts match the data)."""
    meta = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    return CATALOG_DIR / meta["catalog_file"]


def sample_size(text: str) -> int:
    return int(sum(group.count for group in parse_sample_groups(text or "")))


def build_summary(catalog_path: Path) -> pd.DataFrame:
    trait_to_disease = {trait: d.disease_id for d in list_diseases() for trait in d.gwas_traits}
    parts = []
    with zipfile.ZipFile(catalog_path) as archive:
        member = max(archive.infolist(), key=lambda info: info.file_size)
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", dtype=str, usecols=COLUMNS, chunksize=CHUNK_ROWS):
                chunk = chunk[COLUMNS]
                trait = chunk["MAPPED_TRAIT"].fillna("").str.strip().str.lower()
                keep = trait.isin(trait_to_disease)
                if not keep.any():
                    continue
                part = chunk[keep].copy()
                part["disease_id"] = trait[keep].map(trait_to_disease)
                part["rsid"] = part["SNPS"].fillna("").str.strip().str.lower()
                part = part[part["rsid"].str.match(RSID_PATTERN)]
                part["p"] = pd.to_numeric(part["P-VALUE"], errors="coerce")
                part = part[part["p"] > 0]
                parts.append(part[["disease_id", "rsid", "p", "PUBMEDID", "INITIAL SAMPLE SIZE"]])
    rows = pd.concat(parts, ignore_index=True)
    rows["n"] = rows["INITIAL SAMPLE SIZE"].map(sample_size)
    significant = rows[rows["p"] < GENOME_WIDE_P]

    grouped = rows.groupby(["disease_id", "rsid"])
    summary = pd.DataFrame({
        "catalog_best_p_value": grouped["p"].min(),
        "catalog_study_count": grouped["PUBMEDID"].nunique(),
        "catalog_max_sample_size": grouped["n"].max(),
    })
    summary["catalog_gws_study_count"] = significant.groupby(["disease_id", "rsid"])["PUBMEDID"].nunique()
    summary["catalog_gws_study_count"] = summary["catalog_gws_study_count"].fillna(0).astype(int)
    return summary.reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--catalog", type=Path, help="GWAS Catalog snapshot zip (default: the one used for the data)")
    args = parser.parse_args()
    catalog_path = args.catalog or catalog_used_for_dataset()
    summary = build_summary(catalog_path)
    summary.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"Catalog: {catalog_path.name}; {len(summary)} disease-variant pairs -> "
          f"{OUTPUT_FILE.relative_to(RAW_DATA_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
