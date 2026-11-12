from __future__ import annotations

from pathlib import Path
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parent

REQUIRED_DIRECTORIES = [
    "app/assets",
    "app/ui",
    "app/views",
    "core",
    "core/admin",
    "core/ai",
    "data/metadata",
    "data/processed",
    "data/processed/admin_sources",
    "data/processed/backups",
    "data/processed/merge_logs",
    "data/processed/staging",
    "data/raw",
    "data/raw/admin_uploaded",
    "data/raw/online/gwas",
    "data/sample",
    "database",
    "docs",
    "outputs/figures",
    "outputs/models",
    "outputs/tables",
    "pipeline",
]

REQUIRED_FILES = [
    "app/main.py",
    "app/ui/components.py",
    "app/ui/styles.css",
    "app/assets/logo.png",
    "app/views/search.py",
    "app/views/admin.py",
    "core/paths.py",
    "core/auth.py",
    "core/i18n.py",
    "core/search_engine.py",
    "core/glossary.py",
    "core/prs.py",
    "core/admin/data_ingestion.py",
    "core/admin/approval_merge.py",
    "core/admin/final_merge.py",
    "data/processed/ranked_associations_initial.csv",
    "database/snp_platform.db",
]

EXPECTED_TABLES = [
    "Disease",
    "DiseaseSynonym",
    "Gene",
    "SNP",
    "Study",
    "Association",
    "PopulationRegion",
    "UserAccount",
    "AdminActionLog",
]


def rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def create_directories() -> list[str]:
    created = []
    for directory in REQUIRED_DIRECTORIES:
        path = PROJECT_ROOT / directory
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(directory)
    return created


def check_files() -> list[str]:
    return [file_path for file_path in REQUIRED_FILES if not (PROJECT_ROOT / file_path).exists()]


def check_database() -> tuple[bool, list[str], list[tuple[str, int]]]:
    db_path = PROJECT_ROOT / "database" / "snp_platform.db"
    if not db_path.exists():
        return False, EXPECTED_TABLES, []

    with sqlite3.connect(db_path) as conn:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        missing = [table for table in EXPECTED_TABLES if table not in existing]
        counts = []
        for table in sorted(existing):
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}";').fetchone()[0]
            except sqlite3.DatabaseError:
                count = -1
            counts.append((table, count))

    return True, missing, counts


def main() -> int:
    print("SNP-Disease Platform Windows setup check")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    print()

    created_dirs = create_directories()
    if created_dirs:
        print("Created missing directories:")
        for directory in created_dirs:
            print(f"  + {directory}")
    else:
        print("Required directories already exist.")

    print()
    missing_files = check_files()
    if missing_files:
        print("Missing required files:")
        for file_path in missing_files:
            print(f"  ! {file_path}")
    else:
        print("Required files are present.")

    print()
    db_exists, missing_tables, table_counts = check_database()
    if not db_exists:
        print("Database missing: database/snp_platform.db")
    else:
        print("Database present: database/snp_platform.db")
        if missing_tables:
            print("Missing expected database tables:")
            for table in missing_tables:
                print(f"  ! {table}")
        else:
            print("Expected database tables are present.")

        print("Database table counts:")
        for table, count in table_counts:
            print(f"  {table}: {count}")

    print()
    if missing_files or missing_tables or not db_exists:
        print("Setup check completed with warnings. No existing data was overwritten.")
        return 1

    print("Setup check passed. No existing data was overwritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
