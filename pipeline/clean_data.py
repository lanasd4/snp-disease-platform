"""
Initial Data Cleaning Script
"""

from datetime import datetime
import json
import os
import re
import pandas as pd
from core.paths import get_project_root
from core.regions import ancestry_label


# Raw input written by pipeline.extract_from_catalog (override with SNP_RAW_GWAS_FILE).
RAW_GWAS_FILENAME = os.environ.get("SNP_RAW_GWAS_FILE", "gwas_catalog_platform_subset_raw.tsv")
CLEANED_FILENAME = "cleaned_associations_v1.csv"
METADATA_FILENAME = "cleaned_associations_v1_metadata.json"


def get_paths() -> dict:
    """Return important project paths for cleaning."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "raw": project_root / "data" / "raw",
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create required folders if missing."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)

    return paths


def normalize_column_name(column_name: str) -> str:
    """Normalize a source column name for flexible matching."""
    return re.sub(r"[^A-Z0-9]+", "", str(column_name).upper())


def find_column(columns, candidates):
    """Find a source column using multiple possible candidate names."""
    normalized_map = {
        normalize_column_name(column): column
        for column in columns
    }

    for candidate in candidates:
        normalized_candidate = normalize_column_name(candidate)
        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]

    return None


def derive_ancestry(sample_text):
    """Population groups named in a GWAS sample description (or 'Not reported')."""
    return ancestry_label(sample_text)


def clean_text(value):
    """Clean simple text values."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def extract_first_rsid(value):
    """Extract the first rsID from a text."""
    text = clean_text(value)

    if text is None:
        return None

    match = re.search(r"rs\d+", text, flags=re.IGNORECASE)

    if match:
        return match.group(0).lower()

    return None


def extract_risk_allele(value):
    """Extract the risk allele from a value like:"""
    text = clean_text(value)

    if text is None:
        return None

    match = re.search(r"rs\d+\s*[-:]\s*([ACGT]+)", text, flags=re.IGNORECASE)

    if match:
        return match.group(1).upper()

    return None


def to_numeric(value):
    """Convert a value to numeric when possible."""
    if pd.isna(value):
        return None

    value_text = str(value).strip()

    if value_text == "":
        return None

    return pd.to_numeric(value_text, errors="coerce")


def get_series(df: pd.DataFrame, column_name):
    """Return a DataFrame column if it exists."""
    if column_name and column_name in df.columns:
        return df[column_name]

    return pd.Series([None] * len(df), index=df.index)


def build_column_mapping(raw_columns) -> pd.DataFrame:
    """Map source GWAS columns to unified project fields."""
    mapping_specs = [
        {
            "unified_field": "disease_trait",
            "source_candidates": ["DISEASE/TRAIT"]
        },
        {
            "unified_field": "snps_raw",
            "source_candidates": ["SNPS"]
        },
        {
            "unified_field": "strongest_snp_risk_allele_raw",
            "source_candidates": ["STRONGEST SNP-RISK ALLELE"]
        },
        {
            "unified_field": "mapped_gene",
            "source_candidates": ["MAPPED_GENE"]
        },
        {
            "unified_field": "reported_gene",
            "source_candidates": ["REPORTED GENE(S)", "REPORTED GENES"]
        },
        {
            "unified_field": "p_value",
            "source_candidates": ["P-VALUE", "P VALUE"]
        },
        {
            "unified_field": "or_beta_raw",
            "source_candidates": ["OR or BETA", "OR/BETA", "OR BETA"]
        },
        {
            "unified_field": "pubmed_id",
            "source_candidates": ["PUBMEDID", "PUBMED ID"]
        },
        {
            "unified_field": "study_title",
            "source_candidates": ["STUDY"]
        },
        {
            "unified_field": "publication_date",
            "source_candidates": ["DATE"]
        },
        {
            "unified_field": "journal",
            "source_candidates": ["JOURNAL"]
        },
        {
            "unified_field": "initial_sample_size",
            "source_candidates": ["INITIAL SAMPLE SIZE"]
        },
        {
            "unified_field": "replication_sample_size",
            "source_candidates": ["REPLICATION SAMPLE SIZE"]
        },
        {
            # GWAS Catalog REGION is a cytogenetic band (e.g. 7p15.1), not a
            # population; it is kept as chromosome_region. The population
            # (ancestry_region) is derived from INITIAL SAMPLE SIZE instead.
            "unified_field": "chromosome_region",
            "source_candidates": ["REGION"]
        },
        {
            "unified_field": "context",
            "source_candidates": ["CONTEXT"]
        }
    ]

    rows = []

    for spec in mapping_specs:
        matched_column = find_column(raw_columns, spec["source_candidates"])

        rows.append({
            "unified_field": spec["unified_field"],
            "matched_source_column": matched_column,
            "status": "FOUND" if matched_column else "MISSING",
            "source_candidates": " | ".join(spec["source_candidates"])
        })

    return pd.DataFrame(rows)


def create_cleaned_associations() -> dict:
    """Create the first cleaned association file from the raw GWAS sample."""
    paths = ensure_directories()

    raw_path = paths["raw"] / RAW_GWAS_FILENAME

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw GWAS file not found: {raw_path}")

    raw_df = pd.read_csv(raw_path, sep="\t", dtype=str, low_memory=False)

    column_mapping_df = build_column_mapping(raw_df.columns)

    mapping = {
        row["unified_field"]: row["matched_source_column"]
        for _, row in column_mapping_df.iterrows()
    }

    disease_trait_series = get_series(raw_df, mapping.get("disease_trait"))
    snps_raw_series = get_series(raw_df, mapping.get("snps_raw"))
    strongest_series = get_series(raw_df, mapping.get("strongest_snp_risk_allele_raw"))
    mapped_gene_series = get_series(raw_df, mapping.get("mapped_gene"))
    reported_gene_series = get_series(raw_df, mapping.get("reported_gene"))
    p_value_series = get_series(raw_df, mapping.get("p_value"))
    or_beta_series = get_series(raw_df, mapping.get("or_beta_raw"))
    pubmed_series = get_series(raw_df, mapping.get("pubmed_id"))
    study_series = get_series(raw_df, mapping.get("study_title"))
    date_series = get_series(raw_df, mapping.get("publication_date"))
    journal_series = get_series(raw_df, mapping.get("journal"))
    initial_sample_series = get_series(raw_df, mapping.get("initial_sample_size"))
    replication_sample_series = get_series(raw_df, mapping.get("replication_sample_size"))
    chromosome_region_series = get_series(raw_df, mapping.get("chromosome_region"))
    context_series = get_series(raw_df, mapping.get("context"))

    cleaned_df = pd.DataFrame({
        "source_row_number": raw_df.index + 1,
        "disease_trait": disease_trait_series.apply(clean_text),
        "snps_raw": snps_raw_series.apply(clean_text),
        "strongest_snp_risk_allele_raw": strongest_series.apply(clean_text),
        "rsid": snps_raw_series.apply(extract_first_rsid),
        "rsid_from_risk_allele_field": strongest_series.apply(extract_first_rsid),
        "risk_allele": strongest_series.apply(extract_risk_allele),
        "mapped_gene": mapped_gene_series.apply(clean_text),
        "reported_gene": reported_gene_series.apply(clean_text),
        "p_value_raw": p_value_series.apply(clean_text),
        "p_value": p_value_series.apply(to_numeric),
        "or_beta_raw": or_beta_series.apply(clean_text),
        "pubmed_id": pubmed_series.apply(clean_text),
        "study_title": study_series.apply(clean_text),
        "publication_date": date_series.apply(clean_text),
        "journal": journal_series.apply(clean_text),
        "initial_sample_size": initial_sample_series.apply(clean_text),
        "replication_sample_size": replication_sample_series.apply(clean_text),
        "ancestry_region": initial_sample_series.apply(derive_ancestry),
        "chromosome_region": chromosome_region_series.apply(clean_text),
        "context": context_series.apply(clean_text),
        "source_database": "GWAS Catalog"
    })

    # If rsid is missing from SNPS, try to use the strongest SNP-risk allele field.
    cleaned_df["rsid"] = cleaned_df["rsid"].fillna(
        cleaned_df["rsid_from_risk_allele_field"]
    )

    cleaned_df["has_disease_trait"] = cleaned_df["disease_trait"].notna()
    cleaned_df["has_rsid"] = cleaned_df["rsid"].notna()
    cleaned_df["has_p_value"] = cleaned_df["p_value"].notna()
    cleaned_df["has_mapped_gene"] = cleaned_df["mapped_gene"].notna()

    core_mask = (
        cleaned_df["has_disease_trait"]
        & cleaned_df["has_rsid"]
        & cleaned_df["has_p_value"]
    )

    accepted_df = cleaned_df[core_mask].copy()
    rejected_df = cleaned_df[~core_mask].copy()

    accepted_df["cleaning_status"] = "accepted"
    rejected_df["cleaning_status"] = "rejected"

    def build_issue(row):
        issues = []

        if not row["has_disease_trait"]:
            issues.append("missing_disease_trait")

        if not row["has_rsid"]:
            issues.append("missing_rsid")

        if not row["has_p_value"]:
            issues.append("missing_p_value")

        return "; ".join(issues) if issues else "none"

    accepted_df["cleaning_issue"] = "none"
    rejected_df["cleaning_issue"] = rejected_df.apply(build_issue, axis=1)

    cleaned_output_path = paths["processed"] / CLEANED_FILENAME
    rejected_output_path = paths["outputs_tables"] / "rejected_rows.csv"
    preview_output_path = paths["outputs_tables"] / "cleaned_preview.csv"
    report_output_path = paths["outputs_tables"] / "cleaning_report.csv"
    mapping_output_path = paths["outputs_tables"] / "column_mapping.csv"
    top_traits_output_path = paths["outputs_tables"] / "top_disease_traits.csv"

    accepted_df.to_csv(cleaned_output_path, index=False, encoding="utf-8-sig")
    rejected_df.to_csv(rejected_output_path, index=False, encoding="utf-8-sig")
    accepted_df.head(20).to_csv(preview_output_path, index=False, encoding="utf-8-sig")
    column_mapping_df.to_csv(mapping_output_path, index=False, encoding="utf-8-sig")

    top_traits_df = (
        accepted_df["disease_trait"]
        .value_counts()
        .head(20)
        .reset_index()
    )
    top_traits_df.columns = ["disease_trait", "count"]
    top_traits_df.to_csv(top_traits_output_path, index=False, encoding="utf-8-sig")

    report_rows = [
        {"metric": "raw_rows", "value": int(len(raw_df))},
        {"metric": "accepted_rows", "value": int(len(accepted_df))},
        {"metric": "rejected_rows", "value": int(len(rejected_df))},
        {"metric": "raw_columns_count", "value": int(len(raw_df.columns))},
        {"metric": "accepted_columns_count", "value": int(len(accepted_df.columns))},
        {"metric": "missing_rsid_rows", "value": int((~cleaned_df["has_rsid"]).sum())},
        {"metric": "missing_disease_trait_rows", "value": int((~cleaned_df["has_disease_trait"]).sum())},
        {"metric": "missing_p_value_rows", "value": int((~cleaned_df["has_p_value"]).sum())},
        {"metric": "missing_mapped_gene_rows", "value": int((~cleaned_df["has_mapped_gene"]).sum())},
        {"metric": "duplicate_rsid_disease_pairs", "value": int(accepted_df.duplicated(subset=["rsid", "disease_trait"]).sum())},
    ]

    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(report_output_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": CLEANED_FILENAME,
        "source_raw_file": RAW_GWAS_FILENAME,
        "is_real_data": True,
        "is_cleaned_data": True,
        "project_day": 18,
        "stage": "Initial Data Cleaning",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "raw_rows": int(len(raw_df)),
        "accepted_rows": int(len(accepted_df)),
        "rejected_rows": int(len(rejected_df)),
        "core_acceptance_rule": "Rows must have disease_trait, rsid, and p_value.",
        "note": "This is the first cleaned version. Disease normalization will be handled on Day 19."
    }

    metadata_path = paths["processed"] / METADATA_FILENAME

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "raw_rows": len(raw_df),
        "accepted_rows": len(accepted_df),
        "rejected_rows": len(rejected_df),
        "cleaned_output_path": str(cleaned_output_path),
        "metadata_path": str(metadata_path),
        "preview_output_path": str(preview_output_path),
        "report_output_path": str(report_output_path),
        "mapping_output_path": str(mapping_output_path),
        "rejected_output_path": str(rejected_output_path),
        "top_traits_output_path": str(top_traits_output_path)
    }


def main() -> None:
    result = create_cleaned_associations()

    print("Day 18 initial cleaning completed.")
    print(f"Raw rows: {result['raw_rows']}")
    print(f"Accepted rows: {result['accepted_rows']}")
    print(f"Rejected rows: {result['rejected_rows']}")
    print(f"Cleaned file: {result['cleaned_output_path']}")
    print(f"Metadata file: {result['metadata_path']}")
    print(f"Preview file: {result['preview_output_path']}")
    print(f"Cleaning report: {result['report_output_path']}")
    print(f"Column mapping: {result['mapping_output_path']}")
    print(f"Rejected rows: {result['rejected_output_path']}")
    print(f"Top disease traits: {result['top_traits_output_path']}")


if __name__ == "__main__":
    main()
