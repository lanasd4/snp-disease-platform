"""
Association Ranking Features Extraction Script
"""

from datetime import datetime
import json
import math
import sqlite3
import pandas as pd
from core.paths import DATABASE_PATH, get_project_root


RANKING_FEATURES_FILENAME = "ranking_features.csv"
METADATA_FILENAME = "ranking_features_metadata.json"


def get_paths() -> dict:
    """Return important project paths."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "database": DATABASE_PATH,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create required folders if missing."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)

    return paths


def clean_text(value):
    """Clean text values and convert empty-like values to None."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def to_float_or_none(value):
    """Convert value to float when possible."""
    text = clean_text(value)

    if text is None:
        return None

    try:
        return float(text)
    except Exception:
        return None


def bool_like_to_int(value):
    """Convert Y/N, True/False, 1/0 values to 1 or 0."""
    text = str(value).strip().lower()

    if text in ["y", "yes", "true", "1"]:
        return 1

    return 0


def get_table_columns(conn, table_name: str) -> list:
    """Return SQLite table columns."""
    rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
    return [row[1] for row in rows]


def column_expr(conn, table_name: str, alias: str, column_name: str, output_name: str) -> str:
    """Return safe SQL select expression."""
    if column_name in get_table_columns(conn, table_name):
        return f"{alias}.{column_name} AS {output_name}"

    return f"NULL AS {output_name}"


def build_base_association_query(conn) -> str:
    """Build SQL query to read association evidence from the current SQLite schema."""
    assoc_cols = set(get_table_columns(conn, "Association"))
    snp_cols = set(get_table_columns(conn, "SNP"))
    study_cols = set(get_table_columns(conn, "Study"))
    population_cols = set(get_table_columns(conn, "PopulationRegion"))

    if "gene_id" in assoc_cols:
        gene_join = "LEFT JOIN Gene g ON a.gene_id = g.gene_id"
    elif "gene_id" in snp_cols:
        gene_join = "LEFT JOIN Gene g ON s.gene_id = g.gene_id"
    else:
        gene_join = "LEFT JOIN Gene g ON 1 = 0"

    if "study_id" in assoc_cols:
        study_join = "LEFT JOIN Study st ON a.study_id = st.study_id"
    else:
        study_join = "LEFT JOIN Study st ON 1 = 0"

    if "population_region_id" in assoc_cols:
        population_join = "LEFT JOIN PopulationRegion pr ON a.population_region_id = pr.population_region_id"
    else:
        population_join = "LEFT JOIN PopulationRegion pr ON 1 = 0"

    risk_allele_expr = column_expr(conn, "Association", "a", "risk_allele", "risk_allele")
    odds_ratio_expr = column_expr(conn, "Association", "a", "odds_ratio", "odds_ratio")
    effect_size_expr = column_expr(conn, "Association", "a", "effect_size", "effect_size")
    source_expr = column_expr(conn, "Association", "a", "source_database", "source_database")
    evidence_expr = column_expr(conn, "Association", "a", "evidence_level", "evidence_level")

    study_title_expr = "st.study_title AS study_title" if "study_title" in study_cols else "NULL AS study_title"
    pubmed_expr = "st.pubmed_id AS pubmed_id" if "pubmed_id" in study_cols else "NULL AS pubmed_id"
    publication_year_expr = "st.publication_year AS publication_year" if "publication_year" in study_cols else "NULL AS publication_year"
    journal_expr = "st.journal AS journal" if "journal" in study_cols else "NULL AS journal"

    population_label_expr = "pr.population_label AS population_label" if "population_label" in population_cols else "NULL AS population_label"
    region_expr = "pr.region AS region" if "region" in population_cols else "NULL AS region"
    ancestry_expr = "pr.ancestry AS ancestry" if "ancestry" in population_cols else "NULL AS ancestry"
    arab_expr = "pr.is_arab_related AS is_arab_related" if "is_arab_related" in population_cols else "NULL AS is_arab_related"

    query = f"""
    SELECT
        a.rowid AS association_db_rowid,
        d.disease_id AS disease_id,
        d.canonical_name AS disease_name,
        d.arabic_name AS disease_arabic_name,
        s.snp_id AS snp_id,
        s.rsid AS rsid,
        g.gene_id AS gene_id,
        g.gene_symbol AS gene_symbol,
        a.p_value AS p_value,
        {risk_allele_expr},
        {odds_ratio_expr},
        {effect_size_expr},
        {source_expr},
        {evidence_expr},
        {study_title_expr},
        {pubmed_expr},
        {publication_year_expr},
        {journal_expr},
        {population_label_expr},
        {region_expr},
        {ancestry_expr},
        {arab_expr}
    FROM Association a
    JOIN Disease d ON a.disease_id = d.disease_id
    JOIN SNP s ON a.snp_id = s.snp_id
    {gene_join}
    {study_join}
    {population_join}
    """

    return query


def safe_neg_log10(value):
    """Calculate -log10(p-value)."""
    number = to_float_or_none(value)

    if number is None:
        return None

    if number <= 0:
        return None

    try:
        return round(float(-math.log10(number)), 4)
    except Exception:
        return None


def has_value(value) -> int:
    """Return 1 if value exists, otherwise 0."""
    return 1 if clean_text(value) is not None else 0


def build_missing_notes(row) -> str:
    """Build readable notes about missing ranking features."""
    issues = []

    if row.get("p_value_numeric") is None or pd.isna(row.get("p_value_numeric")):
        issues.append("missing_p_value")

    if row.get("has_or_beta") == 0:
        issues.append("missing_or_or_effect_size")

    if row.get("has_risk_allele") == 0:
        issues.append("missing_risk_allele")

    if row.get("has_pubmed_id") == 0:
        issues.append("missing_pubmed_id")

    if row.get("has_population_context") == 0:
        issues.append("missing_population_context")

    return "; ".join(issues) if issues else "none"


def extract_ranking_features() -> dict:
    paths = ensure_directories()

    database_path = paths["database"]

    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    with sqlite3.connect(database_path) as conn:
        query = build_base_association_query(conn)
        base_df = pd.read_sql_query(query, conn)

    if base_df.empty:
        raise ValueError("No Association records found in SQLite.")

    df = base_df.copy()

    df["p_value_numeric"] = df["p_value"].apply(to_float_or_none)
    df["p_value_strength"] = df["p_value"].apply(safe_neg_log10)
    df["p_value_strength_capped"] = df["p_value_strength"].apply(
        lambda x: min(float(x), 300.0) if x is not None and not pd.isna(x) else None
    )

    df["odds_ratio_numeric"] = df["odds_ratio"].apply(to_float_or_none)
    df["effect_size_numeric"] = df["effect_size"].apply(to_float_or_none)

    df["has_or_beta"] = (
        df["odds_ratio_numeric"].notna()
        | df["effect_size_numeric"].notna()
    ).astype(int)

    df["has_risk_allele"] = df["risk_allele"].apply(has_value)
    df["has_pubmed_id"] = df["pubmed_id"].apply(has_value)
    df["has_study_title"] = df["study_title"].apply(has_value)

    df["source_database_clean"] = df["source_database"].apply(
        lambda x: clean_text(x) or "Unknown"
    )

    df["is_arab_related_flag"] = df["is_arab_related"].apply(bool_like_to_int)

    df["has_population_context"] = (
        df["population_label"].apply(has_value)
        | df["region"].apply(has_value)
        | df["ancestry"].apply(has_value)
    ).astype(int)

    # Group features per Disease-SNP pair.
    group_cols = ["disease_id", "snp_id"]

    df["evidence_row_count_for_disease_snp"] = (
        df.groupby(group_cols)["association_db_rowid"].transform("count")
    )

    df["study_count_for_disease_snp"] = (
        df.groupby(group_cols)["study_title"].transform(lambda x: x.dropna().nunique())
    )

    df["population_count_for_disease_snp"] = (
        df.groupby(group_cols)["population_label"].transform(lambda x: x.dropna().nunique())
    )

    df["source_count_for_disease_snp"] = (
        df.groupby(group_cols)["source_database_clean"].transform(lambda x: x.dropna().nunique())
    )

    df["best_p_value_for_disease_snp"] = (
        df.groupby(group_cols)["p_value_numeric"].transform("min")
    )

    df["best_p_value_strength_for_disease_snp"] = (
        df["best_p_value_for_disease_snp"].apply(safe_neg_log10)
    )

    df["has_multiple_evidence_rows"] = (
        df["evidence_row_count_for_disease_snp"] > 1
    ).astype(int)

    df["feature_missing_notes"] = df.apply(build_missing_notes, axis=1)

    df = df.reset_index(drop=True)

    df["ranking_feature_id"] = [
        f"RANKFEAT_{index:06d}"
        for index in range(1, len(df) + 1)
    ]

    output_columns = [
        "ranking_feature_id",
        "association_db_rowid",
        "disease_id",
        "disease_name",
        "disease_arabic_name",
        "snp_id",
        "rsid",
        "gene_id",
        "gene_symbol",
        "p_value",
        "p_value_numeric",
        "p_value_strength",
        "p_value_strength_capped",
        "odds_ratio",
        "odds_ratio_numeric",
        "effect_size",
        "effect_size_numeric",
        "has_or_beta",
        "risk_allele",
        "has_risk_allele",
        "study_title",
        "pubmed_id",
        "publication_year",
        "journal",
        "has_pubmed_id",
        "has_study_title",
        "population_label",
        "region",
        "ancestry",
        "is_arab_related",
        "is_arab_related_flag",
        "has_population_context",
        "source_database_clean",
        "evidence_level",
        "evidence_row_count_for_disease_snp",
        "study_count_for_disease_snp",
        "population_count_for_disease_snp",
        "source_count_for_disease_snp",
        "best_p_value_for_disease_snp",
        "best_p_value_strength_for_disease_snp",
        "has_multiple_evidence_rows",
        "feature_missing_notes"
    ]

    existing_output_columns = [col for col in output_columns if col in df.columns]
    features_df = df[existing_output_columns].copy()

    processed_output_path = paths["processed"] / RANKING_FEATURES_FILENAME
    outputs_output_path = paths["outputs_tables"] / RANKING_FEATURES_FILENAME
    preview_path = paths["outputs_tables"] / "ranking_features_preview.csv"
    summary_path = paths["outputs_tables"] / "ranking_feature_summary.csv"
    missing_report_path = paths["outputs_tables"] / "ranking_missing_values_report.csv"
    metadata_path = paths["processed"] / METADATA_FILENAME

    features_df.to_csv(processed_output_path, index=False, encoding="utf-8-sig")
    features_df.to_csv(outputs_output_path, index=False, encoding="utf-8-sig")
    features_df.head(30).to_csv(preview_path, index=False, encoding="utf-8-sig")

    summary_rows = [
        {"metric": "association_rows", "value": int(len(features_df))},
        {"metric": "unique_diseases", "value": int(features_df["disease_id"].nunique(dropna=True))},
        {"metric": "unique_snps", "value": int(features_df["rsid"].nunique(dropna=True))},
        {"metric": "unique_genes", "value": int(features_df["gene_symbol"].nunique(dropna=True))},
        {"metric": "rows_with_p_value", "value": int(features_df["p_value_numeric"].notna().sum())},
        {"metric": "rows_with_or_or_effect_size", "value": int(features_df["has_or_beta"].sum())},
        {"metric": "rows_with_risk_allele", "value": int(features_df["has_risk_allele"].sum())},
        {"metric": "rows_with_pubmed_id", "value": int(features_df["has_pubmed_id"].sum())},
        {"metric": "rows_with_population_context", "value": int(features_df["has_population_context"].sum())},
        {"metric": "arab_related_rows", "value": int(features_df["is_arab_related_flag"].sum())},
        {"metric": "rows_with_multiple_evidence", "value": int(features_df["has_multiple_evidence_rows"].sum())},
    ]

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    missing_features = [
        "p_value_numeric",
        "odds_ratio_numeric",
        "effect_size_numeric",
        "risk_allele",
        "pubmed_id",
        "study_title",
        "population_label",
        "region",
        "source_database_clean"
    ]

    missing_rows = []

    for feature in missing_features:
        if feature not in features_df.columns:
            continue

        missing_count = int(features_df[feature].isna().sum())
        missing_percent = round((missing_count / len(features_df)) * 100, 2)

        if feature in ["odds_ratio_numeric", "effect_size_numeric"]:
            strategy = "Optional evidence feature. Do not fabricate values; use has_or_beta flag."
        elif feature == "p_value_numeric":
            strategy = "Core feature. Rows without p-value should be excluded or ranked low."
        elif feature == "risk_allele":
            strategy = "Optional feature for PRS/interpretation. Use has_risk_allele flag."
        else:
            strategy = "Context feature. Keep missing as Unknown or use availability flag."

        missing_rows.append({
            "feature_name": feature,
            "missing_count": missing_count,
            "missing_percent": missing_percent,
            "handling_strategy": strategy
        })

    missing_df = pd.DataFrame(missing_rows)
    missing_df.to_csv(missing_report_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": RANKING_FEATURES_FILENAME,
        "stage": "Association Ranking Features",
        "is_ranking_features_file": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "association_rows": int(len(features_df)),
        "unique_diseases": int(features_df["disease_id"].nunique(dropna=True)),
        "unique_snps": int(features_df["rsid"].nunique(dropna=True)),
        "note": "This file prepares ranking features only."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "association_rows": len(features_df),
        "processed_output_path": str(processed_output_path),
        "outputs_output_path": str(outputs_output_path),
        "preview_path": str(preview_path),
        "summary_path": str(summary_path),
        "missing_report_path": str(missing_report_path),
        "metadata_path": str(metadata_path)
    }


def main() -> None:
    result = extract_ranking_features()

    print("Ranking feature extraction completed.")
    print(f"Association rows: {result['association_rows']}")
    print(f"Processed ranking features: {result['processed_output_path']}")
    print(f"Output ranking features: {result['outputs_output_path']}")
    print(f"Preview: {result['preview_path']}")
    print(f"Summary: {result['summary_path']}")
    print(f"Missing values report: {result['missing_report_path']}")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
