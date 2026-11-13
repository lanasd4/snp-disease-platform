"""
Disease Normalization Script
"""

from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
import json
import re
import sqlite3
import pandas as pd
from core.paths import DATABASE_PATH, get_project_root


CLEANED_INPUT_FILENAME = "cleaned_associations_v1.csv"
NORMALIZED_OUTPUT_FILENAME = "normalized_disease_associations.csv"
MATCHED_OUTPUT_FILENAME = "matched_disease_associations.csv"
METADATA_FILENAME = "normalized_disease_associations_metadata.json"


def get_paths() -> dict:
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "database": DATABASE_PATH,
        "processed": project_root / "data" / "processed",
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create required output folders if missing."""
    paths = get_paths()

    paths["processed"].mkdir(parents=True, exist_ok=True)
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)

    return paths


def normalize_text(value) -> str:
    """Normalize Arabic and English text for matching."""
    if pd.isna(value):
        return ""

    text = str(value).strip().lower()

    # Remove Arabic diacritics
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    # Normalize common Arabic letters
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Keep Arabic letters, English letters, and numbers
    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    text = " ".join(text.split())

    return text


def clean_text(value):
    """Clean simple text values."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null"]:
        return None

    return " ".join(text.split())


def load_disease_dictionary(database_path: Path) -> tuple:
    """Load diseases and disease synonyms from SQLite."""
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    with sqlite3.connect(database_path) as conn:
        diseases_df = pd.read_sql_query(
            """
            SELECT
                disease_id,
                canonical_name,
                arabic_name
            FROM Disease
            """,
            conn
        )

        synonyms_df = pd.read_sql_query(
            """
            SELECT
                ds.synonym_id,
                ds.disease_id,
                ds.synonym,
                ds.language,
                ds.synonym_type,
                d.canonical_name,
                d.arabic_name
            FROM DiseaseSynonym ds
            JOIN Disease d ON ds.disease_id = d.disease_id
            """,
            conn
        )

    term_rows = []

    for _, row in diseases_df.iterrows():
        term_rows.append({
            "disease_id": row["disease_id"],
            "canonical_name": row["canonical_name"],
            "arabic_name": row["arabic_name"],
            "term": row["canonical_name"],
            "term_source": "canonical_name"
        })

        if clean_text(row["arabic_name"]):
            term_rows.append({
                "disease_id": row["disease_id"],
                "canonical_name": row["canonical_name"],
                "arabic_name": row["arabic_name"],
                "term": row["arabic_name"],
                "term_source": "arabic_name"
            })

    for _, row in synonyms_df.iterrows():
        term_rows.append({
            "disease_id": row["disease_id"],
            "canonical_name": row["canonical_name"],
            "arabic_name": row["arabic_name"],
            "term": row["synonym"],
            "term_source": f"synonym:{row.get('language', '')}:{row.get('synonym_type', '')}"
        })

    terms_df = pd.DataFrame(term_rows)
    terms_df["normalized_term"] = terms_df["term"].apply(normalize_text)

    # Remove empty normalized terms
    terms_df = terms_df[terms_df["normalized_term"] != ""].copy()

    lookup = {}

    for _, row in terms_df.iterrows():
        key = row["normalized_term"]

        # Keep the first occurrence to avoid unstable duplicate mapping
        if key not in lookup:
            lookup[key] = {
                "disease_id": row["disease_id"],
                "canonical_name": row["canonical_name"],
                "arabic_name": row["arabic_name"],
                "matched_term": row["term"],
                "term_source": row["term_source"]
            }

    return diseases_df, terms_df, lookup


def build_target_keyword_rules(diseases_df: pd.DataFrame) -> list:
    """Build prototype keyword rules for the six target diseases."""
    disease_name_to_id = {
        str(row["canonical_name"]).lower(): row["disease_id"]
        for _, row in diseases_df.iterrows()
    }

    disease_rows = {
        str(row["canonical_name"]).lower(): row
        for _, row in diseases_df.iterrows()
    }

    raw_rules = {
        "type 2 diabetes": [
            "type 2 diabetes",
            "type ii diabetes",
            "diabetes mellitus type 2",
            "diabetes mellitus, type 2",
            "t2d"
        ],
        "obesity": [
            "obesity",
            "body mass index",
            "bmi",
            "waist circumference",
            "adiposity",
            "body fat"
        ],
        "hypertension": [
            "hypertension",
            "blood pressure",
            "systolic blood pressure",
            "diastolic blood pressure"
        ],
        "coronary artery disease": [
            "coronary artery disease",
            "coronary heart disease",
            "myocardial infarction",
            "ischemic heart disease",
            "cad"
        ],
        "chronic kidney disease": [
            "chronic kidney disease",
            "kidney disease",
            "renal function",
            "creatinine",
            "estimated glomerular filtration rate",
            "egfr"
        ],
        "asthma": [
            "asthma",
            "asthmatic"
        ],
        "hypothyroidism": [
            "hypothyroidism",
            "underactive thyroid"
        ],
        "rheumatoid arthritis": [
            "rheumatoid arthritis"
        ],
        "alzheimer's disease": [
            "alzheimer"
        ],
        "breast cancer": [
            "breast cancer",
            "breast carcinoma"
        ]
    }

    rules = []

    for canonical_lower, keywords in raw_rules.items():
        if canonical_lower not in disease_name_to_id:
            continue

        row = disease_rows[canonical_lower]

        for keyword in keywords:
            rules.append({
                "keyword": keyword,
                "normalized_keyword": normalize_text(keyword),
                "disease_id": row["disease_id"],
                "canonical_name": row["canonical_name"],
                "arabic_name": row["arabic_name"]
            })

    # Match longer keywords first
    rules = sorted(rules, key=lambda r: len(r["normalized_keyword"]), reverse=True)

    return rules


def get_best_suggestion(normalized_trait: str, terms_df: pd.DataFrame) -> dict:
    """Suggest the closest disease term for unmatched traits."""
    if normalized_trait == "":
        return {
            "suggested_disease_id": None,
            "suggested_disease_name": None,
            "suggested_term": None,
            "suggestion_score": 0.0
        }

    best_score = 0.0
    best_row = None

    for _, row in terms_df.iterrows():
        score = SequenceMatcher(
            None,
            normalized_trait,
            row["normalized_term"]
        ).ratio()

        if score > best_score:
            best_score = score
            best_row = row

    if best_row is None:
        return {
            "suggested_disease_id": None,
            "suggested_disease_name": None,
            "suggested_term": None,
            "suggestion_score": 0.0
        }

    return {
        "suggested_disease_id": best_row["disease_id"],
        "suggested_disease_name": best_row["canonical_name"],
        "suggested_term": best_row["term"],
        "suggestion_score": round(float(best_score), 3)
    }


def match_disease_trait(trait_value, lookup: dict, terms_df: pd.DataFrame, keyword_rules: list) -> dict:
    """Match one disease_trait value to the platform disease dictionary."""
    original_trait = clean_text(trait_value)
    normalized_trait = normalize_text(original_trait)

    if normalized_trait == "":
        return {
            "disease_id": None,
            "matched_disease_name": None,
            "matched_disease_arabic_name": None,
            "normalized_disease_trait": normalized_trait,
            "matched_term": None,
            "match_method": "missing_trait",
            "match_confidence": 0.0,
            "match_status": "unmatched",
            "needs_manual_review": True,
            **get_best_suggestion(normalized_trait, terms_df)
        }

    # 1. Exact dictionary match
    if normalized_trait in lookup:
        item = lookup[normalized_trait]

        return {
            "disease_id": item["disease_id"],
            "matched_disease_name": item["canonical_name"],
            "matched_disease_arabic_name": item["arabic_name"],
            "normalized_disease_trait": normalized_trait,
            "matched_term": item["matched_term"],
            "match_method": "exact_dictionary_match",
            "match_confidence": 1.0,
            "match_status": "matched",
            "needs_manual_review": False,
            "suggested_disease_id": None,
            "suggested_disease_name": None,
            "suggested_term": None,
            "suggestion_score": None
        }

    # 2. Dictionary containment match
    for term_norm, item in sorted(lookup.items(), key=lambda x: len(x[0]), reverse=True):
        if len(term_norm) < 4:
            continue

        if term_norm in normalized_trait:
            return {
                "disease_id": item["disease_id"],
                "matched_disease_name": item["canonical_name"],
                "matched_disease_arabic_name": item["arabic_name"],
                "normalized_disease_trait": normalized_trait,
                "matched_term": item["matched_term"],
                "match_method": "contains_dictionary_term",
                "match_confidence": 0.9,
                "match_status": "matched",
                "needs_manual_review": False,
                "suggested_disease_id": None,
                "suggested_disease_name": None,
                "suggested_term": None,
                "suggestion_score": None
            }

    # 3. Target-disease keyword rules
    for rule in keyword_rules:
        if rule["normalized_keyword"] and rule["normalized_keyword"] in normalized_trait:
            return {
                "disease_id": rule["disease_id"],
                "matched_disease_name": rule["canonical_name"],
                "matched_disease_arabic_name": rule["arabic_name"],
                "normalized_disease_trait": normalized_trait,
                "matched_term": rule["keyword"],
                "match_method": "target_keyword_rule",
                "match_confidence": 0.8,
                "match_status": "matched",
                "needs_manual_review": True,
                "suggested_disease_id": None,
                "suggested_disease_name": None,
                "suggested_term": None,
                "suggestion_score": None
            }

    # 4. No accepted match, only suggestion
    suggestion = get_best_suggestion(normalized_trait, terms_df)

    return {
        "disease_id": None,
        "matched_disease_name": None,
        "matched_disease_arabic_name": None,
        "normalized_disease_trait": normalized_trait,
        "matched_term": None,
        "match_method": "no_match",
        "match_confidence": 0.0,
        "match_status": "unmatched",
        "needs_manual_review": True,
        **suggestion
    }


def normalize_diseases() -> dict:
    """Normalize disease_trait values in cleaned associations."""
    paths = ensure_directories()

    cleaned_path = paths["processed"] / CLEANED_INPUT_FILENAME
    database_path = paths["database"]

    if not cleaned_path.exists():
        raise FileNotFoundError(f"Cleaned input file not found: {cleaned_path}")

    cleaned_df = pd.read_csv(cleaned_path, dtype=str)

    diseases_df, terms_df, lookup = load_disease_dictionary(database_path)
    keyword_rules = build_target_keyword_rules(diseases_df)

    match_rows = []

    for _, row in cleaned_df.iterrows():
        match_result = match_disease_trait(
            row.get("disease_trait"),
            lookup=lookup,
            terms_df=terms_df,
            keyword_rules=keyword_rules
        )
        match_rows.append(match_result)

    match_df = pd.DataFrame(match_rows)

    normalized_df = pd.concat(
        [
            cleaned_df.reset_index(drop=True),
            match_df.reset_index(drop=True)
        ],
        axis=1
    )

    matched_df = normalized_df[normalized_df["match_status"] == "matched"].copy()
    unmatched_df = normalized_df[normalized_df["match_status"] == "unmatched"].copy()
    review_needed_df = normalized_df[
        normalized_df["needs_manual_review"].astype(str).str.lower() == "true"
    ].copy()

    normalized_output_path = paths["processed"] / NORMALIZED_OUTPUT_FILENAME
    matched_output_path = paths["processed"] / MATCHED_OUTPUT_FILENAME
    metadata_path = paths["processed"] / METADATA_FILENAME

    unmatched_terms_path = paths["outputs_tables"] / "unmatched_disease_terms.csv"
    report_path = paths["outputs_tables"] / "disease_normalization_report.csv"
    preview_path = paths["outputs_tables"] / "matched_disease_preview.csv"
    target_counts_path = paths["outputs_tables"] / "target_disease_counts.csv"
    methods_summary_path = paths["outputs_tables"] / "match_methods_summary.csv"
    review_needed_path = paths["outputs_tables"] / "review_needed_matches.csv"

    normalized_df.to_csv(normalized_output_path, index=False, encoding="utf-8-sig")
    matched_df.to_csv(matched_output_path, index=False, encoding="utf-8-sig")
    matched_df.head(20).to_csv(preview_path, index=False, encoding="utf-8-sig")
    review_needed_df.to_csv(review_needed_path, index=False, encoding="utf-8-sig")

    if unmatched_df.empty:
        unmatched_terms_df = pd.DataFrame(columns=[
            "disease_trait",
            "row_count",
            "suggested_disease_name",
            "suggested_term",
            "suggestion_score"
        ])
    else:
        unmatched_terms_df = (
            unmatched_df
            .groupby("disease_trait", dropna=False)
            .agg(
                row_count=("disease_trait", "size"),
                suggested_disease_name=("suggested_disease_name", "first"),
                suggested_term=("suggested_term", "first"),
                suggestion_score=("suggestion_score", "first")
            )
            .reset_index()
            .sort_values("row_count", ascending=False)
        )

    unmatched_terms_df.to_csv(unmatched_terms_path, index=False, encoding="utf-8-sig")

    if matched_df.empty:
        target_counts_df = pd.DataFrame(columns=["matched_disease_name", "count"])
    else:
        target_counts_df = (
            matched_df["matched_disease_name"]
            .value_counts()
            .reset_index()
        )
        target_counts_df.columns = ["matched_disease_name", "count"]

    target_counts_df.to_csv(target_counts_path, index=False, encoding="utf-8-sig")

    methods_summary_df = (
        normalized_df["match_method"]
        .value_counts()
        .reset_index()
    )
    methods_summary_df.columns = ["match_method", "count"]
    methods_summary_df.to_csv(methods_summary_path, index=False, encoding="utf-8-sig")

    report_rows = [
        {"metric": "input_rows", "value": int(len(cleaned_df))},
        {"metric": "matched_rows", "value": int(len(matched_df))},
        {"metric": "unmatched_rows", "value": int(len(unmatched_df))},
        {"metric": "review_needed_rows", "value": int(len(review_needed_df))},
        {"metric": "unique_input_disease_traits", "value": int(cleaned_df["disease_trait"].nunique(dropna=True))},
        {"metric": "unique_matched_diseases", "value": int(matched_df["matched_disease_name"].nunique(dropna=True)) if not matched_df.empty else 0},
        {"metric": "dictionary_terms_count", "value": int(len(terms_df))},
        {"metric": "target_keyword_rules_count", "value": int(len(keyword_rules))}
    ]

    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(report_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": NORMALIZED_OUTPUT_FILENAME,
        "source_cleaned_file": CLEANED_INPUT_FILENAME,
        "is_real_data": True,
        "is_disease_normalized": True,
        "stage": "Disease Normalization",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_rows": int(len(cleaned_df)),
        "matched_rows": int(len(matched_df)),
        "unmatched_rows": int(len(unmatched_df)),
        "review_needed_rows": int(len(review_needed_df)),
        "matching_methods": methods_summary_df.to_dict(orient="records"),
        "note": "This version maps GWAS disease_trait values to the platform Disease table. Some keyword-rule matches require manual review."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "input_rows": len(cleaned_df),
        "matched_rows": len(matched_df),
        "unmatched_rows": len(unmatched_df),
        "review_needed_rows": len(review_needed_df),
        "normalized_output_path": str(normalized_output_path),
        "matched_output_path": str(matched_output_path),
        "metadata_path": str(metadata_path),
        "unmatched_terms_path": str(unmatched_terms_path),
        "report_path": str(report_path),
        "preview_path": str(preview_path),
        "target_counts_path": str(target_counts_path),
        "methods_summary_path": str(methods_summary_path),
        "review_needed_path": str(review_needed_path)
    }


def main() -> None:
    result = normalize_diseases()

    print("Disease normalization completed.")
    print(f"Input rows: {result['input_rows']}")
    print(f"Matched rows: {result['matched_rows']}")
    print(f"Unmatched rows: {result['unmatched_rows']}")
    print(f"Review needed rows: {result['review_needed_rows']}")
    print(f"Normalized file: {result['normalized_output_path']}")
    print(f"Matched file: {result['matched_output_path']}")
    print(f"Metadata file: {result['metadata_path']}")
    print(f"Unmatched terms: {result['unmatched_terms_path']}")
    print(f"Report: {result['report_path']}")
    print(f"Preview: {result['preview_path']}")
    print(f"Target counts: {result['target_counts_path']}")
    print(f"Match methods summary: {result['methods_summary_path']}")
    print(f"Review needed matches: {result['review_needed_path']}")


if __name__ == "__main__":
    main()
