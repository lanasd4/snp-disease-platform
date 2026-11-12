"""
Deduplication and Entity Linking Script
"""

from datetime import datetime
import json
import re
import pandas as pd
from core.regions import is_middle_eastern
from core.paths import get_project_root


INPUT_ASSOCIATIONS_FILENAME = "associations_normalized_v1.csv"

STUDIES_OUTPUT_FILENAME = "studies_normalized.csv"
POPULATION_OUTPUT_FILENAME = "population_regions_normalized.csv"
ASSOCIATIONS_READY_FILENAME = "associations_ready_for_db.csv"
METADATA_FILENAME = "associations_ready_for_db_metadata.json"


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
    """Clean text values."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def normalize_key(value):
    """Normalize text to create stable matching keys."""
    text = clean_text(value)

    if text is None:
        return ""

    text = text.lower()
    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    text = " ".join(text.split())

    return text


def clean_id(value):
    """Clean IDs that may appear as 1.0 after CSV reading."""
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


def extract_publication_year(publication_date, study_title=None):
    """Extract a four-digit publication year when possible."""
    combined = " ".join([
        str(publication_date) if not pd.isna(publication_date) else "",
        str(study_title) if not pd.isna(study_title) else ""
    ])

    match = re.search(r"(19|20)\d{2}", combined)

    if match:
        return match.group(0)

    return None


def build_study_key(row):
    """Build a stable key for the Study entity."""
    pubmed_id = clean_text(row.get("pubmed_id"))
    study_title = clean_text(row.get("study_title"))

    if pubmed_id:
        return f"pmid:{pubmed_id}"

    if study_title:
        return f"title:{normalize_key(study_title)}"

    return f"unknown_study:{clean_text(row.get('source_row_number'))}"


def build_population_key(row):
    """Build a stable key for PopulationRegion."""
    ancestry_region = clean_text(row.get("ancestry_region"))
    initial_sample_size = clean_text(row.get("initial_sample_size"))

    label_parts = []

    if ancestry_region:
        label_parts.append(ancestry_region)

    if initial_sample_size:
        label_parts.append(initial_sample_size)

    if not label_parts:
        return "unknown_population"

    return normalize_key(" | ".join(label_parts))


def detect_arab_related(row):
    """Arab / Middle Eastern sample flag (core.regions)."""
    text_fields = [
        row.get("ancestry_region"),
        row.get("initial_sample_size"),
        row.get("replication_sample_size"),
        row.get("study_title"),
    ]
    return is_middle_eastern(" ; ".join(str(x) for x in text_fields if not pd.isna(x)))


def build_studies_table(df: pd.DataFrame) -> pd.DataFrame:
    """Build normalized Study staging table."""
    working = df.copy()
    working["study_key"] = working.apply(build_study_key, axis=1)

    study_rows = []

    grouped = working.groupby("study_key", dropna=False)

    for index, (study_key, group) in enumerate(grouped, start=1):
        first = group.iloc[0]

        pubmed_id = clean_text(first.get("pubmed_id"))
        study_title = clean_text(first.get("study_title"))
        publication_date = clean_text(first.get("publication_date"))

        study_rows.append({
            "study_id": f"STUDY_{index:06d}",
            "study_key": study_key,
            "study_title": study_title if study_title else "Unknown study",
            "pubmed_id": pubmed_id,
            "publication_year": extract_publication_year(publication_date, study_title),
            "journal": clean_text(first.get("journal")),
            "source_database": clean_text(first.get("source_database")) or "GWAS Catalog",
            "study_accession": None
        })

    return pd.DataFrame(study_rows)


def build_population_table(df: pd.DataFrame) -> pd.DataFrame:
    """Build PopulationRegion staging table."""
    working = df.copy()
    working["population_key"] = working.apply(build_population_key, axis=1)

    rows = []

    grouped = working.groupby("population_key", dropna=False)

    for index, (population_key, group) in enumerate(grouped, start=1):
        first = group.iloc[0]

        ancestry_region = clean_text(first.get("ancestry_region"))
        initial_sample_size = clean_text(first.get("initial_sample_size"))

        if ancestry_region:
            population_label = ancestry_region
        elif initial_sample_size:
            population_label = initial_sample_size
        else:
            population_label = "Unknown population"

        rows.append({
            "population_region_id": f"POPREG_{index:06d}",
            "population_key": population_key,
            "population_label": population_label,
            "country": None,
            "region": ancestry_region if ancestry_region else "Unknown",
            "ancestry": ancestry_region if ancestry_region else "Unknown",
            "sample_size_text": initial_sample_size,
            "is_arab_related": bool(detect_arab_related(first))
        })

    return pd.DataFrame(rows)


def build_linking_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Build linking issues before final filtering."""
    rows = []

    for _, row in df.iterrows():
        issues = []

        required_fields = {
            "disease_id": row.get("disease_id"),
            "snp_id": row.get("snp_id"),
            "gene_id": row.get("gene_id"),
            "study_id": row.get("study_id"),
            "population_region_id": row.get("population_region_id"),
            "p_value": row.get("p_value")
        }

        for field_name, field_value in required_fields.items():
            if clean_text(field_value) is None:
                issues.append(f"missing_{field_name}")

        if to_float(row.get("p_value")) is None:
            issues.append("invalid_p_value")

        if issues:
            rows.append({
                "association_temp_id": row.get("association_temp_id"),
                "source_row_number": row.get("source_row_number"),
                "disease_id": row.get("disease_id"),
                "rsid": row.get("rsid"),
                "snp_id": row.get("snp_id"),
                "gene_symbol": row.get("gene_symbol"),
                "gene_id": row.get("gene_id"),
                "study_id": row.get("study_id"),
                "population_region_id": row.get("population_region_id"),
                "p_value": row.get("p_value"),
                "linking_issue": "; ".join(issues)
            })

    if rows:
        return pd.DataFrame(rows)

    return pd.DataFrame(columns=[
        "association_temp_id",
        "source_row_number",
        "disease_id",
        "rsid",
        "snp_id",
        "gene_symbol",
        "gene_id",
        "study_id",
        "population_region_id",
        "p_value",
        "linking_issue"
    ])


def run_entity_linking() -> dict:
    paths = ensure_directories()

    input_path = paths["processed"] / INPUT_ASSOCIATIONS_FILENAME

    if not input_path.exists():
        raise FileNotFoundError(f"Day 20 input file not found: {input_path}")

    input_df = pd.read_csv(input_path, dtype=str)

    working_df = input_df.copy()

    # Clean core IDs and numeric p-value
    working_df["disease_id"] = working_df["disease_id"].apply(clean_id)
    working_df["snp_id"] = working_df["snp_id"].apply(clean_id)
    working_df["gene_id"] = working_df["gene_id"].apply(clean_id)
    working_df["p_value_numeric"] = working_df["p_value"].apply(to_float)

    # Build and link Study
    studies_df = build_studies_table(working_df)
    working_df["study_key"] = working_df.apply(build_study_key, axis=1)
    study_lookup = dict(zip(studies_df["study_key"], studies_df["study_id"]))
    working_df["study_id"] = working_df["study_key"].map(study_lookup)

    # Build and link PopulationRegion
    population_df = build_population_table(working_df)
    working_df["population_key"] = working_df.apply(build_population_key, axis=1)
    population_lookup = dict(zip(population_df["population_key"], population_df["population_region_id"]))
    working_df["population_region_id"] = working_df["population_key"].map(population_lookup)

    # Identify linking issues before final filtering
    linking_issues_df = build_linking_issues(working_df)

    ready_mask = (
        working_df["disease_id"].notna()
        & working_df["snp_id"].notna()
        & working_df["gene_id"].notna()
        & working_df["study_id"].notna()
        & working_df["population_region_id"].notna()
        & working_df["p_value_numeric"].notna()
    )

    ready_df = working_df[ready_mask].copy()

    before_dedup_count = len(ready_df)

    dedup_subset = [
        "disease_id",
        "snp_id",
        "gene_id",
        "study_id",
        "population_region_id",
        "p_value",
        "risk_allele"
    ]

    ready_df = ready_df.sort_values(
        by=["disease_id", "rsid", "gene_symbol", "p_value_numeric"],
        ascending=[True, True, True, True]
    ).copy()

    duplicate_mask = ready_df.duplicated(subset=dedup_subset, keep="first")
    duplicates_removed_df = ready_df[duplicate_mask].copy()
    deduped_df = ready_df[~duplicate_mask].copy()

    after_dedup_count = len(deduped_df)

    deduped_df = deduped_df.reset_index(drop=True)

    deduped_df["association_ready_id"] = [
        f"READY_ASSOC_{index:06d}"
        for index in range(1, len(deduped_df) + 1)
    ]

    associations_ready_df = pd.DataFrame({
        "association_ready_id": deduped_df["association_ready_id"],
        "association_temp_id": deduped_df.get("association_temp_id"),
        "source_row_number": deduped_df.get("source_row_number"),
        "disease_id": deduped_df["disease_id"],
        "matched_disease_name": deduped_df.get("matched_disease_name"),
        "matched_disease_arabic_name": deduped_df.get("matched_disease_arabic_name"),
        "snp_id": deduped_df["snp_id"],
        "rsid": deduped_df.get("rsid"),
        "gene_id": deduped_df["gene_id"],
        "gene_symbol": deduped_df.get("gene_symbol"),
        "study_id": deduped_df["study_id"],
        "population_region_id": deduped_df["population_region_id"],
        "p_value": deduped_df["p_value_numeric"],
        "risk_allele": deduped_df.get("risk_allele"),
        "or_beta_raw": deduped_df.get("or_beta_raw"),
        "odds_ratio": deduped_df.get("or_beta_raw").apply(to_float),
        "effect_size": None,
        "pubmed_id": deduped_df.get("pubmed_id"),
        "study_title": deduped_df.get("study_title"),
        "initial_sample_size": deduped_df.get("initial_sample_size"),
        "replication_sample_size": deduped_df.get("replication_sample_size"),
        "ancestry_region": deduped_df.get("ancestry_region"),
        "source_database": deduped_df.get("source_database"),
        "match_method": deduped_df.get("match_method"),
        "needs_manual_review": deduped_df.get("needs_manual_review"),
        "has_multiple_gene_candidates": deduped_df.get("has_multiple_gene_candidates")
    })

    studies_output_path = paths["processed"] / STUDIES_OUTPUT_FILENAME
    population_output_path = paths["processed"] / POPULATION_OUTPUT_FILENAME
    associations_output_path = paths["processed"] / ASSOCIATIONS_READY_FILENAME
    metadata_path = paths["processed"] / METADATA_FILENAME

    report_path = paths["outputs_tables"] / "deduplication_report.csv"
    issues_path = paths["outputs_tables"] / "linking_issues.csv"
    duplicates_path = paths["outputs_tables"] / "duplicate_associations_removed.csv"
    ready_preview_path = paths["outputs_tables"] / "associations_ready_preview.csv"
    studies_preview_path = paths["outputs_tables"] / "studies_preview.csv"
    population_preview_path = paths["outputs_tables"] / "population_regions_preview.csv"

    studies_df.to_csv(studies_output_path, index=False, encoding="utf-8-sig")
    population_df.to_csv(population_output_path, index=False, encoding="utf-8-sig")
    associations_ready_df.to_csv(associations_output_path, index=False, encoding="utf-8-sig")

    linking_issues_df.to_csv(issues_path, index=False, encoding="utf-8-sig")
    duplicates_removed_df.to_csv(duplicates_path, index=False, encoding="utf-8-sig")

    associations_ready_df.head(20).to_csv(ready_preview_path, index=False, encoding="utf-8-sig")
    studies_df.head(20).to_csv(studies_preview_path, index=False, encoding="utf-8-sig")
    population_df.head(20).to_csv(population_preview_path, index=False, encoding="utf-8-sig")

    report_rows = [
        {"metric": "input_association_rows", "value": int(len(input_df))},
        {"metric": "ready_before_dedup_rows", "value": int(before_dedup_count)},
        {"metric": "ready_after_dedup_rows", "value": int(after_dedup_count)},
        {"metric": "duplicates_removed_rows", "value": int(len(duplicates_removed_df))},
        {"metric": "linking_issue_rows", "value": int(len(linking_issues_df))},
        {"metric": "unique_studies", "value": int(len(studies_df))},
        {"metric": "unique_population_regions", "value": int(len(population_df))},
        {"metric": "arab_related_population_regions", "value": int(population_df["is_arab_related"].sum()) if not population_df.empty else 0}
    ]

    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(report_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": ASSOCIATIONS_READY_FILENAME,
        "source_input_file": INPUT_ASSOCIATIONS_FILENAME,
        "project_day": 21,
        "stage": "Deduplication and Entity Linking",
        "is_real_data": True,
        "is_ready_for_db": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_association_rows": int(len(input_df)),
        "ready_before_dedup_rows": int(before_dedup_count),
        "ready_after_dedup_rows": int(after_dedup_count),
        "duplicates_removed_rows": int(len(duplicates_removed_df)),
        "linking_issue_rows": int(len(linking_issues_df)),
        "unique_studies": int(len(studies_df)),
        "unique_population_regions": int(len(population_df)),
        "note": "This file is prepared for database loading. SQLite loading will happen later."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "input_rows": len(input_df),
        "ready_before_dedup_rows": before_dedup_count,
        "ready_after_dedup_rows": after_dedup_count,
        "duplicates_removed_rows": len(duplicates_removed_df),
        "linking_issue_rows": len(linking_issues_df),
        "unique_studies": len(studies_df),
        "unique_population_regions": len(population_df),
        "studies_output_path": str(studies_output_path),
        "population_output_path": str(population_output_path),
        "associations_output_path": str(associations_output_path),
        "metadata_path": str(metadata_path),
        "report_path": str(report_path),
        "issues_path": str(issues_path),
        "duplicates_path": str(duplicates_path)
    }


def main() -> None:
    result = run_entity_linking()

    print("Day 21 entity linking and deduplication completed.")
    print(f"Input rows: {result['input_rows']}")
    print(f"Ready before dedup rows: {result['ready_before_dedup_rows']}")
    print(f"Ready after dedup rows: {result['ready_after_dedup_rows']}")
    print(f"Duplicates removed rows: {result['duplicates_removed_rows']}")
    print(f"Linking issue rows: {result['linking_issue_rows']}")
    print(f"Unique studies: {result['unique_studies']}")
    print(f"Unique population regions: {result['unique_population_regions']}")
    print(f"Studies file: {result['studies_output_path']}")
    print(f"Population regions file: {result['population_output_path']}")
    print(f"Associations ready file: {result['associations_output_path']}")
    print(f"Metadata file: {result['metadata_path']}")
    print(f"Report: {result['report_path']}")
    print(f"Linking issues: {result['issues_path']}")
    print(f"Duplicates removed: {result['duplicates_path']}")


if __name__ == "__main__":
    main()
