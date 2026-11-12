"""
Stage 1 - Extract the platform's disease subset from a local GWAS Catalog copy.

Run:  python -m pipeline.extract_from_catalog [--catalog path/to/snapshot.zip]
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.diseases import list_diseases
from core.regions import is_middle_eastern
from core.paths import RAW_DATA_DIR

GENOME_WIDE_P = 5e-8
SNPS_PER_DISEASE = 150
ARAB_RESERVED_SNPS = 30
MAX_ROWS_PER_SNP = 5
CHUNK_ROWS = 250_000

CATALOG_DIR = RAW_DATA_DIR / "online" / "gwas"
OUTPUT_FILE = RAW_DATA_DIR / "gwas_catalog_platform_subset_raw.tsv"
METADATA_FILE = RAW_DATA_DIR / "gwas_catalog_platform_subset_metadata.json"

RSID_PATTERN = re.compile(r"^rs\d+$", re.IGNORECASE)


def find_latest_catalog() -> Path:
    """Newest full-catalog zip (the large ones; small zips are partial downloads)."""
    candidates = [p for p in CATALOG_DIR.glob("gwas_online_snapshot_*.zip") if p.stat().st_size > 10_000_000]
    if not candidates:
        raise FileNotFoundError(
            f"No full GWAS Catalog snapshot in {CATALOG_DIR}. Download one from the Admin dashboard "
            "(Online updates) or pass --catalog."
        )
    return max(candidates, key=lambda p: p.name)


def read_matching_rows(catalog_path: Path, trait_to_disease: dict) -> pd.DataFrame:
    """Stream the catalog and keep significant single-rsID rows for the wanted traits."""
    parts = []
    with zipfile.ZipFile(catalog_path) as archive:
        member = max(archive.infolist(), key=lambda info: info.file_size)
        with archive.open(member) as handle:
            for chunk in pd.read_csv(handle, sep="\t", dtype=str, chunksize=CHUNK_ROWS, low_memory=False):
                trait = chunk["MAPPED_TRAIT"].fillna("").str.strip().str.lower()
                keep = trait.isin(trait_to_disease)
                if not keep.any():
                    continue
                part = chunk[keep].copy()
                part["_disease_id"] = trait[keep].map(trait_to_disease)
                part["_p"] = pd.to_numeric(part["P-VALUE"], errors="coerce")
                part = part[(part["_p"] > 0) & (part["_p"] < GENOME_WIDE_P)]
                part = part[part["SNPS"].fillna("").str.strip().str.match(RSID_PATTERN)]
                parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def select_snps(rows: pd.DataFrame) -> list:
    """Pick the SNPs for one disease: strongest overall plus reserved Arab/ME slots."""
    rows = rows.assign(_rsid=rows["SNPS"].str.strip().str.lower())
    best = rows.groupby("_rsid")["_p"].min().sort_values()

    arab_rows = rows[rows["INITIAL SAMPLE SIZE"].fillna("").map(is_middle_eastern)]
    arab_best = arab_rows.groupby("_rsid")["_p"].min().sort_values()
    arab_pick = list(arab_best.index[:ARAB_RESERVED_SNPS])

    chosen = list(arab_pick)
    for rsid in best.index:
        if len(chosen) >= SNPS_PER_DISEASE:
            break
        if rsid not in chosen:
            chosen.append(rsid)
    return chosen


def build_subset(catalog_path: Path) -> tuple:
    diseases = list_diseases()
    trait_to_disease = {trait: d.disease_id for d in diseases for trait in d.gwas_traits}
    matches = read_matching_rows(catalog_path, trait_to_disease)

    selected_parts, summary = [], []
    for disease in diseases:
        rows = matches[matches["_disease_id"] == disease.disease_id]
        if rows.empty:
            summary.append({"disease": disease.name_en, "snps": 0, "rows": 0, "arab_rows": 0})
            continue

        chosen = select_snps(rows)
        rows = rows.assign(_rsid=rows["SNPS"].str.strip().str.lower())
        rows = rows[rows["_rsid"].isin(chosen)]
        rows = rows.sort_values("_p").groupby("_rsid", group_keys=False).head(MAX_ROWS_PER_SNP)

        rows = rows.assign(**{"REPORTED_TRAIT": rows["DISEASE/TRAIT"], "DISEASE/TRAIT": disease.name_en})
        selected_parts.append(rows)
        summary.append({
            "disease": disease.name_en,
            "snps": int(rows["_rsid"].nunique()),
            "rows": int(len(rows)),
            "arab_rows": int(rows["INITIAL SAMPLE SIZE"].fillna("").map(is_middle_eastern).sum()),
            "studies": int(rows["STUDY ACCESSION"].nunique()),
        })

    subset = pd.concat(selected_parts, ignore_index=True)
    subset = subset.drop(columns=[c for c in subset.columns if c.startswith("_")])
    return subset, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--catalog", type=Path, help="GWAS Catalog snapshot zip (default: newest)")
    args = parser.parse_args()

    catalog_path = args.catalog or find_latest_catalog()
    subset, summary = build_subset(catalog_path)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    subset.to_csv(OUTPUT_FILE, sep="\t", index=False)
    METADATA_FILE.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "catalog_file": catalog_path.name,
        "p_value_threshold": GENOME_WIDE_P,
        "snps_per_disease": SNPS_PER_DISEASE,
        "arab_reserved_snps": ARAB_RESERVED_SNPS,
        "max_rows_per_snp": MAX_ROWS_PER_SNP,
        "total_rows": int(len(subset)),
        "per_disease": summary,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Catalog: {catalog_path.name}")
    print(pd.DataFrame(summary).to_string(index=False))
    print(f"Wrote {len(subset)} rows -> {OUTPUT_FILE.relative_to(RAW_DATA_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
