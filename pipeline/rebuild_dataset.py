"""
Rebuild the whole dataset (database + processed files) from the GWAS Catalog.

Run:  python -m pipeline.rebuild_dataset [--skip-extract] [--install]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.diseases import list_diseases
from core.paths import (
    DATABASE_DIR,
    DISEASE_SYNONYMS_FILE,
    MASTER_DISEASES_FILE,
    PROJECT_ROOT,
    RANKED_ASSOCIATIONS_FILE,
)

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
LIVE_DB = DATABASE_DIR / "snp_platform.db"
BUILD_DB = DATABASE_DIR / "snp_platform.build.db"
ARCHIVE_DIR = PROJECT_ROOT / "archive" / "local_database"

STAGES = [
    "clean_data",
    "normalize_diseases",
    "normalize_genes_snps",
    "entity_linking",
    "load_processed_data",
    "extract_ranking_features",
    "association_ranking",
    "region_classifier",
]


def run_stage(module: str, env: dict) -> None:
    print(f"\n=== pipeline.{module}", flush=True)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", f"pipeline.{module}"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    tail = "\n".join((result.stdout or "").strip().splitlines()[-6:])
    print(tail)
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(f"Stage pipeline.{module} failed (exit {result.returncode}).")


def create_fresh_database(path: Path) -> None:
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        pd.read_csv(MASTER_DISEASES_FILE, encoding="utf-8-sig").to_sql("Disease", conn, if_exists="append", index=False)
        pd.read_csv(DISEASE_SYNONYMS_FILE, encoding="utf-8-sig").to_sql(
            "DiseaseSynonym", conn, if_exists="append", index=False
        )
    print(f"Fresh database: {path.relative_to(PROJECT_ROOT)}")


def validate(db_path: Path) -> pd.DataFrame:
    """Every registered disease must have associations in the DB and the ranked file."""
    with sqlite3.connect(db_path) as conn:
        db_counts = dict(conn.execute(
            "SELECT d.canonical_name, COUNT(a.association_id) FROM Disease d "
            "LEFT JOIN Association a ON a.disease_id = d.disease_id GROUP BY d.disease_id"
        ).fetchall())
        demo_rows = conn.execute("SELECT COUNT(*) FROM Study WHERE source_name = 'Demo Source'").fetchone()[0]

    ranked = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    report = pd.DataFrame([{
        "disease": d.name_en,
        "db_associations": db_counts.get(d.name_en, 0),
        "ranked_rows": int((ranked["disease_name"] == d.name_en).sum()),
        "ranked_snps": int(ranked.loc[ranked["disease_name"] == d.name_en, "rsid"].nunique()),
    } for d in list_diseases()])

    problems = report[(report["db_associations"] == 0) | (report["ranked_rows"] == 0)]
    if not problems.empty or demo_rows:
        print(report.to_string(index=False))
        raise SystemExit(f"Validation failed: diseases without data={problems['disease'].tolist()}, demo rows={demo_rows}")
    return report


def install(build_db: Path) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if LIVE_DB.exists():
        backup = ARCHIVE_DIR / f"snp_platform_before_rebuild_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.copy2(LIVE_DB, backup)
        print(f"Previous database saved to {backup.relative_to(PROJECT_ROOT)}")
    os.replace(build_db, LIVE_DB)
    print(f"Installed new database: {LIVE_DB.relative_to(PROJECT_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the platform dataset from the GWAS Catalog.")
    parser.add_argument("--skip-extract", action="store_true", help="reuse the existing raw subset")
    parser.add_argument("--install", action="store_true", help="replace database/snp_platform.db when valid")
    args = parser.parse_args()

    env = {**os.environ, "SNP_DATABASE_PATH": str(BUILD_DB), "PYTHONIOENCODING": "utf-8"}

    if not args.skip_extract:
        run_stage("extract_from_catalog", env)
    create_fresh_database(BUILD_DB)
    for stage in STAGES:
        run_stage(stage, env)

    report = validate(BUILD_DB)
    print("\n" + report.to_string(index=False))
    print(f"\nTotal ranked rows: {report['ranked_rows'].sum()}, SNPs: {report['ranked_snps'].sum()}")

    if args.install:
        install(BUILD_DB)
    else:
        print(f"\nBuild kept at {BUILD_DB.relative_to(PROJECT_ROOT)}; run again with --install to use it.")


if __name__ == "__main__":
    main()
