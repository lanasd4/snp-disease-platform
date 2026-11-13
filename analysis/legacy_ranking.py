"""
Frozen copy of the platform's former weighted importance score (before evidence
levels replaced it), kept so the ranking validation can compare both fairly.
Do not edit.
"""

import math

import pandas as pd

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


def legacy_importance_score(df: pd.DataFrame) -> pd.DataFrame:
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

    if missing_best_mask.any():
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
    return ranked_df
