"""
Gene and SNP Normalization Script
"""

from datetime import datetime
import json
import re
import pandas as pd
from core.paths import get_project_root


INPUT_FILENAME = "normalized_disease_associations.csv"

GENES_OUTPUT_FILENAME = "genes_normalized.csv"
SNPS_OUTPUT_FILENAME = "snps_normalized.csv"
ASSOCIATIONS_OUTPUT_FILENAME = "associations_normalized_v1.csv"
METADATA_FILENAME = "associations_normalized_v1_metadata.json"


def get_paths() -> dict:
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create required output folders if missing."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)

    return paths


def clean_text(value):
    """Clean a text value."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def normalize_rsid(value):
    """Extract and normalize rsID."""
    text = clean_text(value)

    if text is None:
        return None

    match = re.search(r"rs\d+", text, flags=re.IGNORECASE)

    if match:
        return match.group(0).lower()

    return None


def split_gene_candidates(value):
    """Split a mapped gene field into possible gene symbols."""
    text = clean_text(value)

    if text is None:
        return []

    parts = re.split(r"\s*[,;]\s*", text)

    cleaned_parts = []

    for part in parts:
        part = part.strip()

        if part == "" or part.lower() in ["nan", "none", "null", "nr"]:
            continue

        cleaned_parts.append(part)

    return cleaned_parts


def normalize_gene_symbol(mapped_gene, reported_gene=None):
    """Select a primary gene symbol."""
    mapped_candidates = split_gene_candidates(mapped_gene)

    if mapped_candidates:
        return mapped_candidates[0].upper()

    reported_candidates = split_gene_candidates(reported_gene)

    if reported_candidates:
        return reported_candidates[0].upper()

    return None


def has_multiple_genes(mapped_gene, reported_gene=None):
    """Detect whether a row may contain more than one gene."""
    mapped_candidates = split_gene_candidates(mapped_gene)
    reported_candidates = split_gene_candidates(reported_gene)

    return len(mapped_candidates) > 1 or len(reported_candidates) > 1


def clean_disease_id(value):
    """Clean disease_id imported from CSV."""
    text = clean_text(value)

    if text is None:
        return None

    if re.fullmatch(r"\d+\.0", text):
        return text.replace(".0", "")

    return text


def to_float(value):
    """Convert a value to float when possible."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "":
        return None

    number = pd.to_numeric(text, errors="coerce")

    if pd.isna(number):
        return None

    return float(number)


def build_gene_table(associations_df: pd.DataFrame) -> pd.DataFrame:
    """Build normalized Gene table from association rows."""
    unique_genes = (
        associations_df["gene_symbol_clean"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    rows = []

    for index, gene_symbol in enumerate(unique_genes, start=1):
        rows.append({
            "gene_id": f"GENE_{index:06d}",
            "gene_symbol": gene_symbol,
            "gene_name": None,
            "description": "Imported from GWAS Catalog mapped_gene field",
            "source_database": "GWAS Catalog"
        })

    return pd.DataFrame(rows)


def build_snp_table(associations_df: pd.DataFrame, genes_df: pd.DataFrame) -> pd.DataFrame:
    """Build normalized SNP table from association rows."""
    gene_lookup = dict(zip(genes_df["gene_symbol"], genes_df["gene_id"]))

    snp_gene_counts = (
        associations_df
        .dropna(subset=["rsid_clean", "gene_symbol_clean"])
        .groupby(["rsid_clean", "gene_symbol_clean"])
        .size()
        .reset_index(name="count")
        .sort_values(["rsid_clean", "count"], ascending=[True, False])
    )

    selected_snp_gene = (
        snp_gene_counts
        .drop_duplicates(subset=["rsid_clean"], keep="first")
        .copy()
    )

    rows = []

    for index, row in enumerate(selected_snp_gene.itertuples(index=False), start=1):
        rsid = row.rsid_clean
        gene_symbol = row.gene_symbol_clean

        rows.append({
            "snp_id": f"SNP_{index:06d}",
            "rsid": rsid,
            "gene_id": gene_lookup.get(gene_symbol),
            "gene_symbol": gene_symbol,
            "chromosome": None,
            "position": None,
            "reference_allele": None,
            "alternate_allele": None,
            "source_database": "GWAS Catalog"
        })

    return pd.DataFrame(rows)


def build_linking_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Build a file explaining why some rows cannot be used for final association linking."""
    rows = []

    for _, row in df.iterrows():
        issues = []

        if str(row.get("match_status", "")).lower() != "matched":
            issues.append("disease_not_matched")

        if clean_disease_id(row.get("disease_id")) is None:
            issues.append("missing_disease_id")

        if normalize_rsid(row.get("rsid")) is None:
            issues.append("missing_or_invalid_rsid")

        gene_symbol = normalize_gene_symbol(
            row.get("mapped_gene"),
            row.get("reported_gene")
        )

        if gene_symbol is None:
            issues.append("missing_gene_symbol")

        if to_float(row.get("p_value")) is None:
            issues.append("missing_or_invalid_p_value")

        if issues:
            rows.append({
                "source_row_number": row.get("source_row_number"),
                "disease_trait": row.get("disease_trait"),
                "match_status": row.get("match_status"),
                "disease_id": row.get("disease_id"),
                "rsid": row.get("rsid"),
                "mapped_gene": row.get("mapped_gene"),
                "reported_gene": row.get("reported_gene"),
                "p_value": row.get("p_value"),
                "linking_issue": "; ".join(issues)
            })

    return pd.DataFrame(rows)


def normalize_genes_and_snps() -> dict:
    paths = ensure_directories()

    input_path = paths["processed"] / INPUT_FILENAME

    if not input_path.exists():
        raise FileNotFoundError(f"Day 19 input file not found: {input_path}")

    input_df = pd.read_csv(input_path, dtype=str)

    working_df = input_df.copy()

    working_df["disease_id_clean"] = working_df["disease_id"].apply(clean_disease_id)
    working_df["rsid_clean"] = working_df["rsid"].apply(normalize_rsid)
    working_df["gene_symbol_clean"] = working_df.apply(
        lambda row: normalize_gene_symbol(
            row.get("mapped_gene"),
            row.get("reported_gene")
        ),
        axis=1
    )
    working_df["p_value_clean"] = working_df["p_value"].apply(to_float)
    working_df["has_multiple_gene_candidates"] = working_df.apply(
        lambda row: has_multiple_genes(
            row.get("mapped_gene"),
            row.get("reported_gene")
        ),
        axis=1
    )

    usable_mask = (
        (working_df["match_status"].astype(str).str.lower() == "matched")
        & working_df["disease_id_clean"].notna()
        & working_df["rsid_clean"].notna()
        & working_df["gene_symbol_clean"].notna()
        & working_df["p_value_clean"].notna()
    )

    usable_df = working_df[usable_mask].copy()

    linking_issues_df = build_linking_issues(working_df)

    genes_df = build_gene_table(usable_df)
    snps_df = build_snp_table(usable_df, genes_df)

    gene_lookup = dict(zip(genes_df["gene_symbol"], genes_df["gene_id"]))
    snp_lookup = dict(zip(snps_df["rsid"], snps_df["snp_id"]))

    associations_df = usable_df.copy()

    associations_df["gene_id"] = associations_df["gene_symbol_clean"].map(gene_lookup)
    associations_df["snp_id"] = associations_df["rsid_clean"].map(snp_lookup)

    associations_df = associations_df[
        associations_df["gene_id"].notna()
        & associations_df["snp_id"].notna()
    ].copy()

    associations_df = associations_df.reset_index(drop=True)

    associations_df["association_temp_id"] = [
        f"ASSOC_{index:06d}"
        for index in range(1, len(associations_df) + 1)
    ]

    associations_output_df = pd.DataFrame({
        "association_temp_id": associations_df["association_temp_id"],
        "source_row_number": associations_df.get("source_row_number"),
        "disease_id": associations_df["disease_id_clean"],
        "matched_disease_name": associations_df.get("matched_disease_name"),
        "matched_disease_arabic_name": associations_df.get("matched_disease_arabic_name"),
        "snp_id": associations_df["snp_id"],
        "rsid": associations_df["rsid_clean"],
        "gene_id": associations_df["gene_id"],
        "gene_symbol": associations_df["gene_symbol_clean"],
        "p_value": associations_df["p_value_clean"],
        "risk_allele": associations_df.get("risk_allele"),
        "or_beta_raw": associations_df.get("or_beta_raw"),
        "pubmed_id": associations_df.get("pubmed_id"),
        "study_title": associations_df.get("study_title"),
        "publication_date": associations_df.get("publication_date"),
        "journal": associations_df.get("journal"),
        "initial_sample_size": associations_df.get("initial_sample_size"),
        "replication_sample_size": associations_df.get("replication_sample_size"),
        "ancestry_region": associations_df.get("ancestry_region"),
        "source_database": associations_df.get("source_database"),
        "match_method": associations_df.get("match_method"),
        "needs_manual_review": associations_df.get("needs_manual_review"),
        "has_multiple_gene_candidates": associations_df["has_multiple_gene_candidates"]
    })

    multi_gene_df = associations_output_df[
        associations_output_df["has_multiple_gene_candidates"].astype(str).str.lower() == "true"
    ].copy()

    genes_output_path = paths["processed"] / GENES_OUTPUT_FILENAME
    snps_output_path = paths["processed"] / SNPS_OUTPUT_FILENAME
    associations_output_path = paths["processed"] / ASSOCIATIONS_OUTPUT_FILENAME
    metadata_path = paths["processed"] / METADATA_FILENAME

    report_path = paths["outputs_tables"] / "gene_snp_normalization_report.csv"
    genes_preview_path = paths["outputs_tables"] / "genes_preview.csv"
    snps_preview_path = paths["outputs_tables"] / "snps_preview.csv"
    associations_preview_path = paths["outputs_tables"] / "associations_preview.csv"
    issues_path = paths["outputs_tables"] / "linking_issues.csv"
    multi_gene_path = paths["outputs_tables"] / "multi_gene_snp_review.csv"

    genes_df.to_csv(genes_output_path, index=False, encoding="utf-8-sig")
    snps_df.to_csv(snps_output_path, index=False, encoding="utf-8-sig")
    associations_output_df.to_csv(associations_output_path, index=False, encoding="utf-8-sig")

    genes_df.head(20).to_csv(genes_preview_path, index=False, encoding="utf-8-sig")
    snps_df.head(20).to_csv(snps_preview_path, index=False, encoding="utf-8-sig")
    associations_output_df.head(20).to_csv(associations_preview_path, index=False, encoding="utf-8-sig")

    linking_issues_df.to_csv(issues_path, index=False, encoding="utf-8-sig")
    multi_gene_df.to_csv(multi_gene_path, index=False, encoding="utf-8-sig")

    report_rows = [
        {"metric": "input_rows", "value": int(len(input_df))},
        {"metric": "usable_association_rows", "value": int(len(associations_output_df))},
        {"metric": "unique_genes", "value": int(len(genes_df))},
        {"metric": "unique_snps", "value": int(len(snps_df))},
        {"metric": "linking_issue_rows", "value": int(len(linking_issues_df))},
        {"metric": "multi_gene_review_rows", "value": int(len(multi_gene_df))},
        {"metric": "missing_gene_rows", "value": int(working_df["gene_symbol_clean"].isna().sum())},
        {"metric": "missing_rsid_rows", "value": int(working_df["rsid_clean"].isna().sum())},
        {"metric": "missing_disease_id_rows", "value": int(working_df["disease_id_clean"].isna().sum())},
        {"metric": "invalid_p_value_rows", "value": int(working_df["p_value_clean"].isna().sum())}
    ]

    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(report_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": ASSOCIATIONS_OUTPUT_FILENAME,
        "source_input_file": INPUT_FILENAME,
        "project_day": 20,
        "stage": "Gene and SNP Normalization",
        "is_real_data": True,
        "is_gene_snp_normalized": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_rows": int(len(input_df)),
        "usable_association_rows": int(len(associations_output_df)),
        "unique_genes": int(len(genes_df)),
        "unique_snps": int(len(snps_df)),
        "linking_issue_rows": int(len(linking_issues_df)),
        "note": "gene_id, snp_id, and association_temp_id are staging identifiers for processed CSV files. Final database IDs may be assigned during SQLite loading."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "input_rows": len(input_df),
        "usable_association_rows": len(associations_output_df),
        "unique_genes": len(genes_df),
        "unique_snps": len(snps_df),
        "linking_issue_rows": len(linking_issues_df),
        "multi_gene_review_rows": len(multi_gene_df),
        "genes_output_path": str(genes_output_path),
        "snps_output_path": str(snps_output_path),
        "associations_output_path": str(associations_output_path),
        "metadata_path": str(metadata_path),
        "report_path": str(report_path),
        "issues_path": str(issues_path),
        "multi_gene_path": str(multi_gene_path)
    }


def main() -> None:
    result = normalize_genes_and_snps()

    print("Day 20 Gene and SNP normalization completed.")
    print(f"Input rows: {result['input_rows']}")
    print(f"Usable association rows: {result['usable_association_rows']}")
    print(f"Unique genes: {result['unique_genes']}")
    print(f"Unique SNPs: {result['unique_snps']}")
    print(f"Linking issue rows: {result['linking_issue_rows']}")
    print(f"Multi-gene review rows: {result['multi_gene_review_rows']}")
    print(f"Genes file: {result['genes_output_path']}")
    print(f"SNPs file: {result['snps_output_path']}")
    print(f"Associations file: {result['associations_output_path']}")
    print(f"Metadata file: {result['metadata_path']}")
    print(f"Report: {result['report_path']}")
    print(f"Linking issues: {result['issues_path']}")
    print(f"Multi-gene review: {result['multi_gene_path']}")


if __name__ == "__main__":
    main()
