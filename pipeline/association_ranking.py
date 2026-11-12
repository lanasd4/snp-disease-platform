"""
Rule-Based Association Ranking Script
"""

from datetime import datetime
import json
import math
import pandas as pd
from core.paths import get_project_root


INPUT_FEATURES_FILENAME = "ranking_features.csv"
RANKED_OUTPUT_FILENAME = "ranked_associations_initial.csv"
METADATA_FILENAME = "ranked_associations_initial_metadata.json"


RANKING_WEIGHTS = {
    "p_value_strength_score": 45,
    "evidence_count_score": 15,
    "study_count_score": 10,
    "population_count_score": 8,
    "source_count_score": 5,
    "or_beta_score": 5,
    "risk_allele_score": 5,
    "pubmed_score": 4,
    "arab_related_bonus": 3
}


def get_paths() -> dict:
    """Return important project paths."""
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
    """Clean text and convert empty-like values to None."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null", "nr"]:
        return None

    return " ".join(text.split())


def to_float_or_zero(value):
    """Convert value to float. If impossible, return 0.0."""
    text = clean_text(value)

    if text is None:
        return 0.0

    try:
        number = float(text)
        if math.isnan(number):
            return 0.0
        return number
    except Exception:
        return 0.0


def to_int_flag(value):
    """Convert values like 1, true, y to 1; otherwise 0."""
    text = str(value).strip().lower()

    if text in ["1", "true", "yes", "y"]:
        return 1

    return 0


def safe_log_scaled_score(value, max_value):
    """Scale count-like values using log1p."""
    number = max(to_float_or_zero(value), 0.0)
    max_number = max(float(max_value), 1.0)

    denominator = math.log1p(max_number)

    if denominator == 0:
        return 0.0

    return round(math.log1p(number) / denominator, 4)


def p_value_strength_component(value):
    """Convert p_value_strength into a 0-1 score."""
    strength = max(to_float_or_zero(value), 0.0)

    return round(min(strength / 100.0, 1.0), 4)


def assign_rank_label(score):
    """Assign a readable rank label based on importance_score."""
    score = to_float_or_zero(score)

    if score >= 85:
        return "Very High"

    if score >= 70:
        return "High"

    if score >= 50:
        return "Moderate"

    return "Low"


def assign_arabic_rank_label(score):
    """Assign Arabic label for easier explanation."""
    score = to_float_or_zero(score)

    if score >= 85:
        return "قوي جدًا"

    if score >= 70:
        return "قوي"

    if score >= 50:
        return "متوسط"

    return "منخفض"


def build_score_explanation(row):
    """Build a short explanation of why the score was assigned."""
    parts = []

    if to_float_or_zero(row.get("p_value_strength_score")) >= 0.8:
        parts.append("very strong p-value evidence")
    elif to_float_or_zero(row.get("p_value_strength_score")) >= 0.5:
        parts.append("moderate-to-strong p-value evidence")
    else:
        parts.append("limited p-value strength")

    if to_int_flag(row.get("has_multiple_evidence_rows")) == 1:
        parts.append("supported by multiple evidence rows")

    if to_float_or_zero(row.get("study_count_for_disease_snp")) > 1:
        parts.append("appears in multiple studies")

    if to_int_flag(row.get("has_risk_allele")) == 1:
        parts.append("risk allele available")

    if to_int_flag(row.get("has_or_beta")) == 1:
        parts.append("OR/effect size available")

    if to_int_flag(row.get("is_arab_related_flag")) == 1:
        parts.append("Arab-related context detected")

    return "; ".join(parts)


def build_arabic_score_explanation(row):
    """Build short Arabic explanation for the score."""
    parts = []

    if to_float_or_zero(row.get("p_value_strength_score")) >= 0.8:
        parts.append("دليل إحصائي قوي جدًا حسب p-value")
    elif to_float_or_zero(row.get("p_value_strength_score")) >= 0.5:
        parts.append("دليل إحصائي متوسط إلى قوي")
    else:
        parts.append("قوة إحصائية محدودة نسبيًا")

    if to_int_flag(row.get("has_multiple_evidence_rows")) == 1:
        parts.append("مدعوم بأكثر من سجل دليل")

    if to_float_or_zero(row.get("study_count_for_disease_snp")) > 1:
        parts.append("ظهر في أكثر من دراسة")

    if to_int_flag(row.get("has_risk_allele")) == 1:
        parts.append("يتوفر risk allele")

    if to_int_flag(row.get("has_or_beta")) == 1:
        parts.append("تتوفر قيمة OR أو effect size")

    if to_int_flag(row.get("is_arab_related_flag")) == 1:
        parts.append("يوجد سياق عربي/إقليمي")

    return "؛ ".join(parts)


def calculate_ranking(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate rule-based ranking scores."""
    ranked_df = df.copy()

    numeric_columns = [
        "p_value_strength",
        "best_p_value_strength_for_disease_snp",
        "evidence_row_count_for_disease_snp",
        "study_count_for_disease_snp",
        "population_count_for_disease_snp",
        "source_count_for_disease_snp",
        "has_or_beta",
        "has_risk_allele",
        "has_pubmed_id",
        "is_arab_related_flag",
        "has_multiple_evidence_rows"
    ]

    for col in numeric_columns:
        if col not in ranked_df.columns:
            ranked_df[col] = 0

    # Use best p-value strength for the Disease-SNP pair when available.
    ranked_df["ranking_p_value_strength"] = ranked_df[
        "best_p_value_strength_for_disease_snp"
    ].apply(to_float_or_zero)

    missing_best_mask = ranked_df["ranking_p_value_strength"] == 0

    ranked_df.loc[missing_best_mask, "ranking_p_value_strength"] = ranked_df.loc[
        missing_best_mask,
        "p_value_strength"
    ].apply(to_float_or_zero)

    max_evidence = max(ranked_df["evidence_row_count_for_disease_snp"].apply(to_float_or_zero).max(), 1)
    max_study = max(ranked_df["study_count_for_disease_snp"].apply(to_float_or_zero).max(), 1)
    max_population = max(ranked_df["population_count_for_disease_snp"].apply(to_float_or_zero).max(), 1)
    max_source = max(ranked_df["source_count_for_disease_snp"].apply(to_float_or_zero).max(), 1)

    ranked_df["p_value_strength_score"] = ranked_df["ranking_p_value_strength"].apply(
        p_value_strength_component
    )

    ranked_df["evidence_count_score"] = ranked_df["evidence_row_count_for_disease_snp"].apply(
        lambda value: safe_log_scaled_score(value, max_evidence)
    )

    ranked_df["study_count_score"] = ranked_df["study_count_for_disease_snp"].apply(
        lambda value: safe_log_scaled_score(value, max_study)
    )

    ranked_df["population_count_score"] = ranked_df["population_count_for_disease_snp"].apply(
        lambda value: safe_log_scaled_score(value, max_population)
    )

    ranked_df["source_count_score"] = ranked_df["source_count_for_disease_snp"].apply(
        lambda value: safe_log_scaled_score(value, max_source)
    )

    ranked_df["or_beta_score"] = ranked_df["has_or_beta"].apply(to_int_flag)
    ranked_df["risk_allele_score"] = ranked_df["has_risk_allele"].apply(to_int_flag)
    ranked_df["pubmed_score"] = ranked_df["has_pubmed_id"].apply(to_int_flag)
    ranked_df["arab_related_bonus"] = ranked_df["is_arab_related_flag"].apply(to_int_flag)

    ranked_df["importance_score"] = (
        ranked_df["p_value_strength_score"] * RANKING_WEIGHTS["p_value_strength_score"]
        + ranked_df["evidence_count_score"] * RANKING_WEIGHTS["evidence_count_score"]
        + ranked_df["study_count_score"] * RANKING_WEIGHTS["study_count_score"]
        + ranked_df["population_count_score"] * RANKING_WEIGHTS["population_count_score"]
        + ranked_df["source_count_score"] * RANKING_WEIGHTS["source_count_score"]
        + ranked_df["or_beta_score"] * RANKING_WEIGHTS["or_beta_score"]
        + ranked_df["risk_allele_score"] * RANKING_WEIGHTS["risk_allele_score"]
        + ranked_df["pubmed_score"] * RANKING_WEIGHTS["pubmed_score"]
        + ranked_df["arab_related_bonus"] * RANKING_WEIGHTS["arab_related_bonus"]
    )

    ranked_df["importance_score"] = ranked_df["importance_score"].round(2)
    ranked_df["rank_label"] = ranked_df["importance_score"].apply(assign_rank_label)
    ranked_df["rank_label_arabic"] = ranked_df["importance_score"].apply(assign_arabic_rank_label)

    ranked_df["score_explanation"] = ranked_df.apply(build_score_explanation, axis=1)
    ranked_df["score_explanation_arabic"] = ranked_df.apply(build_arabic_score_explanation, axis=1)

    ranked_df = ranked_df.sort_values(
        by=["disease_id", "importance_score", "ranking_p_value_strength"],
        ascending=[True, False, False]
    ).copy()

    ranked_df["rank_position_within_disease"] = (
        ranked_df.groupby("disease_id")["importance_score"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )

    ranked_df = ranked_df.reset_index(drop=True)

    ranked_df["ranked_association_id"] = [
        f"RANKED_ASSOC_{index:06d}"
        for index in range(1, len(ranked_df) + 1)
    ]

    return ranked_df


def create_top_snps_per_disease(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """Create one best row per Disease-SNP pair, then rank top SNPs inside each disease."""
    sort_cols = ["disease_id", "rsid", "importance_score", "ranking_p_value_strength"]

    top_df = ranked_df.sort_values(
        by=sort_cols,
        ascending=[True, True, False, False]
    ).copy()

    top_df = top_df.drop_duplicates(
        subset=["disease_id", "rsid"],
        keep="first"
    ).copy()

    top_df = top_df.sort_values(
        by=["disease_id", "importance_score", "ranking_p_value_strength"],
        ascending=[True, False, False]
    ).copy()

    top_df["top_snp_rank_within_disease"] = (
        top_df.groupby("disease_id")["importance_score"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )

    columns = [
        "top_snp_rank_within_disease",
        "disease_id",
        "disease_name",
        "disease_arabic_name",
        "rsid",
        "gene_symbol",
        "importance_score",
        "rank_label",
        "rank_label_arabic",
        "p_value",
        "p_value_strength",
        "evidence_row_count_for_disease_snp",
        "study_count_for_disease_snp",
        "population_count_for_disease_snp",
        "source_count_for_disease_snp",
        "has_or_beta",
        "has_risk_allele",
        "is_arab_related_flag",
        "score_explanation_arabic"
    ]

    existing_cols = [col for col in columns if col in top_df.columns]

    return top_df[existing_cols].copy()


def create_score_summary(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """Create overall score summary by disease."""
    summary_df = (
        ranked_df
        .groupby(["disease_id", "disease_name"], dropna=False)
        .agg(
            association_rows=("ranked_association_id", "count"),
            unique_snps=("rsid", "nunique"),
            average_score=("importance_score", "mean"),
            max_score=("importance_score", "max"),
            min_score=("importance_score", "min")
        )
        .reset_index()
    )

    summary_df["average_score"] = summary_df["average_score"].round(2)
    summary_df["max_score"] = summary_df["max_score"].round(2)
    summary_df["min_score"] = summary_df["min_score"].round(2)

    return summary_df.sort_values("max_score", ascending=False)


def create_component_summary(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """Create average component scores for review."""
    component_columns = [
        "p_value_strength_score",
        "evidence_count_score",
        "study_count_score",
        "population_count_score",
        "source_count_score",
        "or_beta_score",
        "risk_allele_score",
        "pubmed_score",
        "arab_related_bonus"
    ]

    rows = []

    for col in component_columns:
        if col not in ranked_df.columns:
            continue

        rows.append({
            "component": col,
            "weight": RANKING_WEIGHTS.get(col, None),
            "average_component_value_0_to_1": round(float(ranked_df[col].mean()), 4),
            "max_component_value_0_to_1": round(float(ranked_df[col].max()), 4),
            "min_component_value_0_to_1": round(float(ranked_df[col].min()), 4)
        })

    return pd.DataFrame(rows)


def run_rule_based_ranking() -> dict:
    paths = ensure_directories()

    input_path = paths["processed"] / INPUT_FEATURES_FILENAME

    if not input_path.exists():
        raise FileNotFoundError(f"Ranking features file not found: {input_path}")

    features_df = pd.read_csv(input_path, dtype=str)

    if features_df.empty:
        raise ValueError("ranking_features.csv is empty.")

    ranked_df = calculate_ranking(features_df)
    top_snps_df = create_top_snps_per_disease(ranked_df)
    score_summary_df = create_score_summary(ranked_df)
    component_summary_df = create_component_summary(ranked_df)

    processed_output_path = paths["processed"] / RANKED_OUTPUT_FILENAME
    outputs_output_path = paths["outputs_tables"] / RANKED_OUTPUT_FILENAME
    preview_path = paths["outputs_tables"] / "ranked_associations_preview.csv"
    top_snps_path = paths["outputs_tables"] / "top_snps_per_disease.csv"
    score_summary_path = paths["outputs_tables"] / "ranking_score_summary.csv"
    component_summary_path = paths["outputs_tables"] / "ranking_component_summary.csv"
    metadata_path = paths["processed"] / METADATA_FILENAME

    ranked_df.to_csv(processed_output_path, index=False, encoding="utf-8-sig")
    ranked_df.to_csv(outputs_output_path, index=False, encoding="utf-8-sig")
    ranked_df.head(50).to_csv(preview_path, index=False, encoding="utf-8-sig")
    top_snps_df.to_csv(top_snps_path, index=False, encoding="utf-8-sig")
    score_summary_df.to_csv(score_summary_path, index=False, encoding="utf-8-sig")
    component_summary_df.to_csv(component_summary_path, index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": RANKED_OUTPUT_FILENAME,
        "project_day": 26,
        "stage": "Rule-Based Association Ranking",
        "is_ranked_associations_file": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_rows": int(len(features_df)),
        "ranked_rows": int(len(ranked_df)),
        "unique_diseases": int(ranked_df["disease_id"].nunique(dropna=True)),
        "unique_snps": int(ranked_df["rsid"].nunique(dropna=True)),
        "score_weights": RANKING_WEIGHTS,
        "note": "Initial rule-based ranking on real data. This ranking is for research prioritization, not medical diagnosis."
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    return {
        "input_rows": len(features_df),
        "ranked_rows": len(ranked_df),
        "processed_output_path": str(processed_output_path),
        "outputs_output_path": str(outputs_output_path),
        "preview_path": str(preview_path),
        "top_snps_path": str(top_snps_path),
        "score_summary_path": str(score_summary_path),
        "component_summary_path": str(component_summary_path),
        "metadata_path": str(metadata_path)
    }


def main() -> None:
    result = run_rule_based_ranking()

    print("Day 26 rule-based ranking completed.")
    print(f"Input rows: {result['input_rows']}")
    print(f"Ranked rows: {result['ranked_rows']}")
    print(f"Processed ranked associations: {result['processed_output_path']}")
    print(f"Output ranked associations: {result['outputs_output_path']}")
    print(f"Preview: {result['preview_path']}")
    print(f"Top SNPs per disease: {result['top_snps_path']}")
    print(f"Score summary: {result['score_summary_path']}")
    print(f"Component summary: {result['component_summary_path']}")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
