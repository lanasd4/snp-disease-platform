"""
Processed Data Loading Script
"""

from datetime import datetime
import json
import sqlite3
import pandas as pd
from core.paths import DATABASE_PATH, get_project_root


GENES_FILE = "genes_normalized.csv"
SNPS_FILE = "snps_normalized.csv"
STUDIES_FILE = "studies_normalized.csv"
POPULATION_FILE = "population_regions_normalized.csv"
ASSOCIATIONS_FILE = "associations_ready_for_db.csv"


def get_paths() -> dict:
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "database": DATABASE_PATH,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create output folders if missing."""
    paths = get_paths()
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)
    return paths


def clean_text(value):
    """Clean text values before database insertion."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def to_int_or_none(value):
    """Convert a value to integer when possible."""
    text = clean_text(value)

    if text is None:
        return None

    try:
        return int(float(text))
    except Exception:
        return None


def to_float_or_none(value):
    """Convert a value to float when possible."""
    text = clean_text(value)

    if text is None:
        return None

    try:
        return float(text)
    except Exception:
        return None


def bool_to_int(value):
    """Convert boolean-like values to Y or N for the current SQLite schema."""
    text = str(value).strip().lower()

    if text in ["true", "1", "yes", "y"]:
        return "Y"

    return "N"


def get_table_columns(conn, table_name):
    """Return list of column names for a SQLite table."""
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    return [row[1] for row in rows]


def get_primary_key_column(conn, table_name):
    """Return primary key column name for a SQLite table."""
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()

    for row in rows:
        # PRAGMA table_info:
        # cid, name, type, notnull, default_value, pk
        if row[5] == 1:
            return row[1]

    return None


def apply_schema_defaults(table_name: str, row_data: dict, table_columns: set) -> dict:
    """Add safe default values for required schema fields when they exist in the table."""
    row_data = dict(row_data)

    def is_missing(value):
        if value is None:
            return True
        text = str(value).strip()
        return text == "" or text.lower() in ["nan", "none", "null", "nr"]

    def set_if_needed(column_name, default_value):
        if column_name in table_columns and (
            column_name not in row_data or is_missing(row_data.get(column_name))
        ):
            row_data[column_name] = default_value

    # General active flag used by the existing schema.
    # In this database active accepts Y/N, not 1/0.
    set_if_needed("active", "Y")

    if table_name == "Gene":
        gene_symbol = row_data.get("gene_symbol") or "Unknown gene"
        set_if_needed("gene_name", gene_symbol)
        set_if_needed("description", f"Imported gene symbol {gene_symbol} from GWAS Catalog")

    elif table_name == "SNP":
        set_if_needed("variant_type", "SNP")
        set_if_needed("chromosome", "Unknown")
        set_if_needed("position", "Unknown")
        set_if_needed("reference_allele", "N")
        set_if_needed("alternate_allele", "N")

    elif table_name == "Study":
        set_if_needed("study_title", "Unknown study")
        set_if_needed("source_database", "GWAS Catalog")
        set_if_needed("source_name", "GWAS Catalog")

    elif table_name == "PopulationRegion":
        set_if_needed("population_label", "Unknown population")
        set_if_needed("country", "Unknown")
        set_if_needed("region", "Unknown")
        set_if_needed("ancestry", "Unknown")
        set_if_needed("is_arab_related", "N")

    elif table_name == "Association":
        set_if_needed("source_database", "GWAS Catalog")
        set_if_needed("evidence_level", "Real GWAS imported data")
        set_if_needed("clinical_significance", "Not provided")

    return row_data


def insert_filtered_row(conn, table_name, row_data: dict):
    """Insert a row into a table using only columns that actually exist."""
    table_columns = set(get_table_columns(conn, table_name))

    row_data = apply_schema_defaults(table_name, row_data, table_columns)

    filtered = {
        key: value
        for key, value in row_data.items()
        if key in table_columns and value is not None
    }

    if not filtered:
        raise ValueError(f"No valid columns to insert into {table_name}")

    columns = list(filtered.keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)

    values = [filtered[col] for col in columns]

    sql = f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})"
    cursor = conn.execute(sql, values)

    return cursor.lastrowid


def find_one_by_conditions(conn, table_name, conditions: dict):
    """Find one row primary key by matching available columns."""
    pk_col = get_primary_key_column(conn, table_name)

    if pk_col is None:
        raise ValueError(f"No primary key found for table {table_name}")

    table_columns = set(get_table_columns(conn, table_name))

    clauses = []
    values = []

    for col, value in conditions.items():
        if col in table_columns and value is not None:
            clauses.append(f"{col} = ?")
            values.append(value)

    if not clauses:
        return None

    sql = f"SELECT {pk_col} FROM {table_name} WHERE {' AND '.join(clauses)} LIMIT 1"
    row = conn.execute(sql, values).fetchone()

    if row:
        return row[0]

    return None


def table_count(conn, table_name):
    """Count rows in a table."""
    return conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()[0]


def load_genes(conn, genes_df):
    """Load genes into the Gene table."""
    mapping = {}
    inserted = 0
    existing = 0

    for _, row in genes_df.iterrows():
        staging_id = clean_text(row.get("gene_id"))
        gene_symbol = clean_text(row.get("gene_symbol"))

        if gene_symbol is None:
            continue

        existing_id = find_one_by_conditions(
            conn,
            "Gene",
            {"gene_symbol": gene_symbol}
        )

        if existing_id is not None:
            db_id = existing_id
            existing += 1
        else:
            db_id = insert_filtered_row(
                conn,
                "Gene",
                {
                    "gene_symbol": gene_symbol,
                    "gene_name": clean_text(row.get("gene_name")) or gene_symbol,
                    "description": clean_text(row.get("description")) or f"Imported gene symbol {gene_symbol} from GWAS Catalog",
                    "active": "Y",
                }
            )
            inserted += 1

        mapping[staging_id] = db_id

    return mapping, inserted, existing


def load_snps(conn, snps_df, gene_mapping):
    """Load SNPs into the SNP table."""
    mapping = {}
    inserted = 0
    existing = 0
    issues = []

    for _, row in snps_df.iterrows():
        staging_id = clean_text(row.get("snp_id"))
        rsid = clean_text(row.get("rsid"))
        staging_gene_id = clean_text(row.get("gene_id"))
        db_gene_id = gene_mapping.get(staging_gene_id)

        if rsid is None:
            issues.append({
                "entity": "SNP",
                "staging_id": staging_id,
                "issue": "missing_rsid"
            })
            continue

        if db_gene_id is None:
            issues.append({
                "entity": "SNP",
                "staging_id": staging_id,
                "issue": "missing_gene_mapping"
            })
            continue

        existing_id = find_one_by_conditions(
            conn,
            "SNP",
            {"rsid": rsid}
        )

        if existing_id is not None:
            db_id = existing_id
            existing += 1
        else:
            db_id = insert_filtered_row(
                conn,
                "SNP",
                {
                    "rsid": rsid,
                    "gene_id": db_gene_id,
                    "chromosome": clean_text(row.get("chromosome")),
                    "position": clean_text(row.get("position")),
                    "reference_allele": clean_text(row.get("reference_allele")),
                    "alternate_allele": clean_text(row.get("alternate_allele")),
                }
            )
            inserted += 1

        mapping[staging_id] = db_id

    return mapping, inserted, existing, issues


def load_studies(conn, studies_df, default_population_region_id=None):
    """Load studies into the Study table."""
    mapping = {}
    inserted = 0
    existing = 0

    table_columns = set(get_table_columns(conn, "Study"))

    for _, row in studies_df.iterrows():
        staging_id = clean_text(row.get("study_id"))
        study_title = clean_text(row.get("study_title"))
        pubmed_id = clean_text(row.get("pubmed_id"))

        existing_id = None

        if "pubmed_id" in table_columns and pubmed_id:
            existing_id = find_one_by_conditions(
                conn,
                "Study",
                {"pubmed_id": pubmed_id}
            )

        if existing_id is None and study_title:
            existing_id = find_one_by_conditions(
                conn,
                "Study",
                {"study_title": study_title}
            )

        if existing_id is not None:
            db_id = existing_id
            existing += 1
        else:
            source_database = clean_text(row.get("source_database")) or "GWAS Catalog"

            insert_data = {
                "study_title": study_title,
                "pubmed_id": pubmed_id,
                "publication_year": to_int_or_none(row.get("publication_year")),
                "journal": clean_text(row.get("journal")),
                "source_database": source_database,
                "source_name": source_database,
                "study_accession": clean_text(row.get("study_accession")),
                "population_region_id": default_population_region_id,
            }

            db_id = insert_filtered_row(conn, "Study", insert_data)
            inserted += 1

        mapping[staging_id] = db_id

    return mapping, inserted, existing


def load_population_regions(conn, population_df):
    """Load population regions into PopulationRegion table."""
    mapping = {}
    inserted = 0
    existing = 0

    for _, row in population_df.iterrows():
        staging_id = clean_text(row.get("population_region_id"))
        population_label = clean_text(row.get("population_label")) or "Unknown population"
        region = clean_text(row.get("region")) or "Unknown"

        existing_id = find_one_by_conditions(
            conn,
            "PopulationRegion",
            {
                "population_label": population_label,
                "region": region
            }
        )

        if existing_id is None:
            existing_id = find_one_by_conditions(
                conn,
                "PopulationRegion",
                {
                    "population_label": population_label
                }
            )

        if existing_id is not None:
            db_id = existing_id
            existing += 1
        else:
            db_id = insert_filtered_row(
                conn,
                "PopulationRegion",
                {
                    "population_label": population_label,
                    "country": clean_text(row.get("country")),
                    "region": region,
                    "ancestry": clean_text(row.get("ancestry")),
                    "is_arab_related": bool_to_int(row.get("is_arab_related")),
                }
            )
            inserted += 1

        mapping[staging_id] = db_id

    return mapping, inserted, existing


def association_exists(conn, assoc_data):
    """Check whether an association already exists."""
    table_columns = set(get_table_columns(conn, "Association"))

    conditions = {
        "disease_id": assoc_data.get("disease_id"),
        "snp_id": assoc_data.get("snp_id"),
        "gene_id": assoc_data.get("gene_id"),
        "study_id": assoc_data.get("study_id"),
        "population_region_id": assoc_data.get("population_region_id"),
    }

    filtered = {
        col: value
        for col, value in conditions.items()
        if col in table_columns and value is not None
    }

    if not filtered:
        return False

    clauses = [f"{col} = ?" for col in filtered.keys()]
    values = list(filtered.values())

    sql = f"SELECT COUNT(*) FROM Association WHERE {' AND '.join(clauses)}"
    count = conn.execute(sql, values).fetchone()[0]

    return count > 0


def load_associations(conn, ready_df, gene_mapping, snp_mapping, study_mapping, population_mapping):
    """Load ready associations into Association table."""
    inserted = 0
    existing = 0
    issues = []

    for _, row in ready_df.iterrows():
        staging_gene_id = clean_text(row.get("gene_id"))
        staging_snp_id = clean_text(row.get("snp_id"))
        staging_study_id = clean_text(row.get("study_id"))
        staging_pop_id = clean_text(row.get("population_region_id"))

        db_gene_id = gene_mapping.get(staging_gene_id)
        db_snp_id = snp_mapping.get(staging_snp_id)
        db_study_id = study_mapping.get(staging_study_id)
        db_population_id = population_mapping.get(staging_pop_id)

        disease_id = to_int_or_none(row.get("disease_id"))
        p_value = to_float_or_none(row.get("p_value"))

        missing = []

        if disease_id is None:
            missing.append("disease_id")

        if db_gene_id is None:
            missing.append("gene_id_mapping")

        if db_snp_id is None:
            missing.append("snp_id_mapping")

        if db_study_id is None:
            missing.append("study_id_mapping")

        if db_population_id is None:
            missing.append("population_region_id_mapping")

        if p_value is None:
            missing.append("p_value")

        if missing:
            issues.append({
                "association_ready_id": clean_text(row.get("association_ready_id")),
                "rsid": clean_text(row.get("rsid")),
                "gene_symbol": clean_text(row.get("gene_symbol")),
                "issue": "; ".join(missing)
            })
            continue

        assoc_data = {
            "disease_id": disease_id,
            "snp_id": db_snp_id,
            "gene_id": db_gene_id,
            "study_id": db_study_id,
            "population_region_id": db_population_id,
            "p_value": p_value,
            "odds_ratio": to_float_or_none(row.get("odds_ratio")),
            "effect_size": to_float_or_none(row.get("effect_size")),
            "risk_allele": clean_text(row.get("risk_allele")),
            "effect_allele": None,
            "source_database": clean_text(row.get("source_database")) or "GWAS Catalog",
            "evidence_level": "Real GWAS imported data",
            "clinical_significance": None,
        }

        if association_exists(conn, assoc_data):
            existing += 1
            continue

        insert_filtered_row(conn, "Association", assoc_data)
        inserted += 1

    return inserted, existing, issues


def create_id_mapping_preview(gene_mapping, snp_mapping, study_mapping, population_mapping):
    """Create a small DataFrame showing staging ID to database ID mapping."""
    rows = []

    for staging_id, db_id in list(gene_mapping.items())[:20]:
        rows.append({
            "entity_type": "Gene",
            "staging_id": staging_id,
            "database_id": db_id
        })

    for staging_id, db_id in list(snp_mapping.items())[:20]:
        rows.append({
            "entity_type": "SNP",
            "staging_id": staging_id,
            "database_id": db_id
        })

    for staging_id, db_id in list(study_mapping.items())[:20]:
        rows.append({
            "entity_type": "Study",
            "staging_id": staging_id,
            "database_id": db_id
        })

    for staging_id, db_id in list(population_mapping.items())[:20]:
        rows.append({
            "entity_type": "PopulationRegion",
            "staging_id": staging_id,
            "database_id": db_id
        })

    return pd.DataFrame(rows)


def create_table_counts(conn):
    """Create counts for key project tables after loading."""
    tables = [
        "Disease",
        "DiseaseSynonym",
        "Gene",
        "SNP",
        "Study",
        "PopulationRegion",
        "Association"
    ]

    rows = []

    for table in tables:
        rows.append({
            "table_name": table,
            "row_count": table_count(conn, table)
        })

    return pd.DataFrame(rows)


def create_real_data_search_preview(conn):
    """Create a quick search preview from imported real data."""
    assoc_cols = set(get_table_columns(conn, "Association"))
    study_cols = set(get_table_columns(conn, "Study"))
    pop_cols = set(get_table_columns(conn, "PopulationRegion"))

    study_title_expr = "st.study_title" if "study_title" in study_cols else "NULL"
    source_expr = "a.source_database" if "source_database" in assoc_cols else "'GWAS Catalog'"
    region_expr = "pr.region" if "region" in pop_cols else "NULL"
    pop_label_expr = "pr.population_label" if "population_label" in pop_cols else "NULL"

    gene_join = ""
    gene_select = "NULL AS gene_symbol"

    if "gene_id" in assoc_cols:
        gene_join = "LEFT JOIN Gene g ON a.gene_id = g.gene_id"
        gene_select = "g.gene_symbol AS gene_symbol"
    else:
        gene_join = "LEFT JOIN Gene g ON s.gene_id = g.gene_id"
        gene_select = "g.gene_symbol AS gene_symbol"

    sql = f"""
    SELECT
        d.canonical_name AS disease_name,
        d.arabic_name AS disease_arabic_name,
        s.rsid AS rsid,
        {gene_select},
        a.p_value AS p_value,
        a.risk_allele AS risk_allele,
        {study_title_expr} AS study_title,
        {pop_label_expr} AS population_label,
        {region_expr} AS region,
        {source_expr} AS source_database
    FROM Association a
    JOIN Disease d ON a.disease_id = d.disease_id
    JOIN SNP s ON a.snp_id = s.snp_id
    {gene_join}
    LEFT JOIN Study st ON a.study_id = st.study_id
    LEFT JOIN PopulationRegion pr ON a.population_region_id = pr.population_region_id
    ORDER BY a.p_value ASC
    LIMIT 50;
    """

    return pd.read_sql_query(sql, conn)


def run_database_loading() -> dict:
    paths = ensure_directories()

    database_path = paths["database"]

    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    genes_df = pd.read_csv(paths["processed"] / GENES_FILE, dtype=str)
    snps_df = pd.read_csv(paths["processed"] / SNPS_FILE, dtype=str)
    studies_df = pd.read_csv(paths["processed"] / STUDIES_FILE, dtype=str)
    population_df = pd.read_csv(paths["processed"] / POPULATION_FILE, dtype=str)
    ready_df = pd.read_csv(paths["processed"] / ASSOCIATIONS_FILE, dtype=str)

    issues = []

    with sqlite3.connect(database_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        create_table_counts(conn)

        gene_mapping, genes_inserted, genes_existing = load_genes(conn, genes_df)
        snp_mapping, snps_inserted, snps_existing, snp_issues = load_snps(conn, snps_df, gene_mapping)

        # Load PopulationRegion before Study because the current SQLite Study schema
        # requires population_region_id as a NOT NULL field.
        population_mapping, populations_inserted, populations_existing = load_population_regions(conn, population_df)

        default_population_region_id = None
        if population_mapping:
            default_population_region_id = list(population_mapping.values())[0]

        study_mapping, studies_inserted, studies_existing = load_studies(
            conn,
            studies_df,
            default_population_region_id=default_population_region_id
        )

        issues.extend(snp_issues)

        associations_inserted, associations_existing, association_issues = load_associations(
            conn,
            ready_df,
            gene_mapping,
            snp_mapping,
            study_mapping,
            population_mapping
        )

        issues.extend(association_issues)

        conn.commit()

        after_counts_df = create_table_counts(conn)
        search_preview_df = create_real_data_search_preview(conn)

    summary_rows = [
        {"metric": "genes_input_rows", "value": int(len(genes_df))},
        {"metric": "genes_inserted", "value": int(genes_inserted)},
        {"metric": "genes_existing", "value": int(genes_existing)},
        {"metric": "snps_input_rows", "value": int(len(snps_df))},
        {"metric": "snps_inserted", "value": int(snps_inserted)},
        {"metric": "snps_existing", "value": int(snps_existing)},
        {"metric": "studies_input_rows", "value": int(len(studies_df))},
        {"metric": "studies_inserted", "value": int(studies_inserted)},
        {"metric": "studies_existing", "value": int(studies_existing)},
        {"metric": "population_input_rows", "value": int(len(population_df))},
        {"metric": "population_inserted", "value": int(populations_inserted)},
        {"metric": "population_existing", "value": int(populations_existing)},
        {"metric": "associations_input_rows", "value": int(len(ready_df))},
        {"metric": "associations_inserted", "value": int(associations_inserted)},
        {"metric": "associations_existing_or_skipped", "value": int(associations_existing)},
        {"metric": "loading_issue_rows", "value": int(len(issues))}
    ]

    summary_df = pd.DataFrame(summary_rows)

    issues_df = pd.DataFrame(issues)

    if issues_df.empty:
        issues_df = pd.DataFrame(columns=["entity", "staging_id", "association_ready_id", "rsid", "gene_symbol", "issue"])

    mapping_preview_df = create_id_mapping_preview(
        gene_mapping,
        snp_mapping,
        study_mapping,
        population_mapping
    )

    summary_path = paths["outputs_tables"] / "db_load_summary.csv"
    counts_path = paths["outputs_tables"] / "table_counts_after_load.csv"
    search_preview_path = paths["outputs_tables"] / "real_data_search_preview.csv"
    mapping_preview_path = paths["outputs_tables"] / "inserted_id_mappings_preview.csv"
    issues_path = paths["outputs_tables"] / "database_loading_issues.csv"

    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    after_counts_df.to_csv(counts_path, index=False, encoding="utf-8-sig")
    search_preview_df.to_csv(search_preview_path, index=False, encoding="utf-8-sig")
    mapping_preview_df.to_csv(mapping_preview_path, index=False, encoding="utf-8-sig")
    issues_df.to_csv(issues_path, index=False, encoding="utf-8-sig")

    metadata = {
        "project_day": 22,
        "stage": "Database Loading",
        "is_real_data_loaded_to_sqlite": True,
        "database_file": str(database_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary_df.to_dict(orient="records"),
        "note": "Processed real-data CSV files were loaded into SQLite. Existing records are reused where possible."
    }

    metadata_path = paths["processed"] / "database_loading_metadata.json"

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "summary_path": str(summary_path),
        "counts_path": str(counts_path),
        "search_preview_path": str(search_preview_path),
        "mapping_preview_path": str(mapping_preview_path),
        "issues_path": str(issues_path),
        "metadata_path": str(metadata_path),
        "associations_inserted": associations_inserted,
        "associations_existing": associations_existing,
        "loading_issue_rows": len(issues)
    }


def main() -> None:
    result = run_database_loading()

    print("Day 22 processed data loading completed.")
    print(f"Associations inserted: {result['associations_inserted']}")
    print(f"Associations existing/skipped: {result['associations_existing']}")
    print(f"Loading issue rows: {result['loading_issue_rows']}")
    print(f"Summary: {result['summary_path']}")
    print(f"Table counts: {result['counts_path']}")
    print(f"Search preview: {result['search_preview_path']}")
    print(f"ID mapping preview: {result['mapping_preview_path']}")
    print(f"Issues: {result['issues_path']}")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
