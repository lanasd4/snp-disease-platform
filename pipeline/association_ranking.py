"""
Stage - Assign evidence levels to every association (core.evidence) and write
the ranked file used by the app.

Run:  python -m pipeline.association_ranking
"""

import json
from datetime import datetime

import pandas as pd

from core.evidence import GENOME_WIDE_P, SUGGESTIVE_P, TIER_ORDER, assign_evidence
from core.paths import get_project_root

INPUT_FEATURES_FILENAME = "ranking_features.csv"
RANKED_OUTPUT_FILENAME = "ranked_associations_initial.csv"
METADATA_FILENAME = "ranked_associations_initial_metadata.json"


def get_paths() -> dict:
    root = get_project_root()
    paths = {
        "processed": root / "data" / "processed",
        "outputs_tables": root / "outputs" / "tables",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def calculate_ranking(df: pd.DataFrame) -> pd.DataFrame:
    """Evidence levels and within-disease order (kept under this name for callers)."""
    return assign_evidence(df)


def create_top_snps_per_disease(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """Best row per disease-variant pair, in evidence order."""
    top = ranked_df.drop_duplicates(subset=["disease_id", "rsid"], keep="first").copy()
    top["top_snp_rank_within_disease"] = top.groupby("disease_id").cumcount() + 1
    columns = ["top_snp_rank_within_disease", "disease_id", "disease_name", "disease_arabic_name", "rsid",
               "gene_symbol", "rank_label", "rank_label_arabic", "independent_gws_studies", "best_p_value",
               "effect_magnitude", "max_sample_size", "is_arab_related_flag", "score_explanation_arabic"]
    return top[[c for c in columns if c in top.columns]]


def create_tier_summary(ranked_df: pd.DataFrame) -> pd.DataFrame:
    pairs = ranked_df.drop_duplicates(subset=["disease_id", "rsid"])
    table = pd.crosstab(pairs["disease_name"], pairs["rank_label"]).reindex(columns=TIER_ORDER, fill_value=0)
    table["variants"] = table.sum(axis=1)
    return table.reset_index()


def run_rule_based_ranking() -> dict:
    paths = get_paths()
    input_path = paths["processed"] / INPUT_FEATURES_FILENAME
    if not input_path.exists():
        raise FileNotFoundError(f"Ranking features file not found: {input_path}")

    features_df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    if features_df.empty:
        raise ValueError("ranking_features.csv is empty.")

    ranked_df = calculate_ranking(features_df)
    top_snps_df = create_top_snps_per_disease(ranked_df)
    tier_summary_df = create_tier_summary(ranked_df)

    processed_output_path = paths["processed"] / RANKED_OUTPUT_FILENAME
    ranked_df.to_csv(processed_output_path, index=False, encoding="utf-8-sig")
    ranked_df.to_csv(paths["outputs_tables"] / RANKED_OUTPUT_FILENAME, index=False, encoding="utf-8-sig")
    top_snps_df.to_csv(paths["outputs_tables"] / "top_snps_per_disease.csv", index=False, encoding="utf-8-sig")
    tier_summary_df.to_csv(paths["outputs_tables"] / "evidence_level_summary.csv", index=False, encoding="utf-8-sig")

    metadata = {
        "file_name": RANKED_OUTPUT_FILENAME,
        "stage": "Evidence levels",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ranked_rows": int(len(ranked_df)),
        "unique_diseases": int(ranked_df["disease_id"].nunique()),
        "unique_snps": int(ranked_df["rsid"].nunique()),
        "evidence_levels": {
            "Confirmed": f"p < {GENOME_WIDE_P:g} in >= 2 independent studies (whole GWAS Catalog)",
            "Strong": f"p < {GENOME_WIDE_P:g} in one study",
            "Suggestive": f"p < {SUGGESTIVE_P:g}",
        },
        "order": ["best p-value (whole catalog)", "evidence level", "effect size |log OR| or |beta|",
                  "largest sample size"],
        "levels_by_variant": tier_summary_df.set_index("disease_name")[TIER_ORDER].to_dict(orient="index"),
        "note": "Research prioritisation, not medical diagnosis.",
    }
    (paths["processed"] / METADATA_FILENAME).write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")
    return {"ranked_rows": len(ranked_df), "processed_output_path": str(processed_output_path)}


def main() -> None:
    result = run_rule_based_ranking()
    print(f"Ranked {result['ranked_rows']} associations -> {result['processed_output_path']}")


if __name__ == "__main__":
    main()
