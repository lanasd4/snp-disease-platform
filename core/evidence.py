"""
Evidence levels for variant-disease associations.

Instead of a weighted score, each association gets a transparent evidence level
built on standard GWAS criteria:

  3  Confirmed   genome-wide significant (p < 5e-8) in two or more independent studies
  2  Strong      genome-wide significant in one study
  1  Suggestive  p < 1e-5
  0  Below threshold

Two separate questions, two separate fields:
  * how strong is the evidence?  -> results are ordered by the best p-value in
    the whole catalog, then evidence level, effect size and sample size;
  * how reliable is it?          -> the evidence level (replication), shown as a
    badge and filter.
Ordering by p-value first ranks established disease genes higher than ordering by
level first (analysis/ranking_validation.py). Arab-population evidence is a
separate flag, never part of the level.
Replication is counted over the whole GWAS Catalog (see pipeline.evidence_summary),
plus any independent studies added through the admin dashboard.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from core.paths import PROCESSED_DATA_DIR

GENOME_WIDE_P = 5e-8
SUGGESTIVE_P = 1e-5
EVIDENCE_SUMMARY_FILE = PROCESSED_DATA_DIR / "evidence_summary.csv"

TIER_CONFIRMED, TIER_STRONG, TIER_SUGGESTIVE, TIER_BELOW = 3, 2, 1, 0
TIER_LABELS = {
    TIER_CONFIRMED: ("Confirmed", "مؤكَّد"),
    TIER_STRONG: ("Strong", "قوي"),
    TIER_SUGGESTIVE: ("Suggestive", "مقترح"),
    TIER_BELOW: ("Below threshold", "دون العتبة"),
}
LABEL_TO_TIER = {label: tier for tier, pair in TIER_LABELS.items() for label in pair}
TIER_ORDER = ["Confirmed", "Strong", "Suggestive", "Below threshold"]

# Columns written by assign_evidence (replacing the old weighted-score columns).
EVIDENCE_COLUMNS = [
    "best_p_value", "independent_gws_studies", "independent_studies", "max_sample_size", "effect_magnitude",
    "evidence_tier", "rank_label", "rank_label_arabic", "score_explanation", "score_explanation_arabic",
    "rank_position_within_disease", "ranked_association_id",
]
OBSOLETE_COLUMNS = [
    "ranking_p_value_strength", "p_value_strength_score", "evidence_count_score", "study_count_score",
    "population_count_score", "source_count_score", "or_beta_score", "risk_allele_score", "pubmed_score",
    "arab_related_bonus", "importance_score",
]


def arabic_studies(n: int, adjective: str = "مستقلة") -> str:
    """Arabic count of studies with correct number agreement."""
    n = int(n)
    adj = f" {adjective}" if adjective else ""
    if n == 1:
        return f"دراسة واحدة{adj}"
    if n == 2:
        return f"دراستين{' مستقلتين' if adjective else ''}"
    if 3 <= n <= 10:
        return f"{n} دراسات{adj}"
    return f"{n} دراسة{adj}"


def tier_for(best_p: float, gws_studies: int) -> int:
    if best_p is None or not best_p > 0 or math.isnan(best_p):
        return TIER_BELOW
    if best_p < GENOME_WIDE_P:
        return TIER_CONFIRMED if gws_studies >= 2 else TIER_STRONG
    return TIER_SUGGESTIVE if best_p < SUGGESTIVE_P else TIER_BELOW


def tier_label(value, arabic: bool = False) -> str:
    """Display label for a tier number or an English/Arabic label."""
    try:
        tier = int(float(value))
    except (TypeError, ValueError):
        tier = LABEL_TO_TIER.get(str(value).strip(), TIER_BELOW)
    english, arab = TIER_LABELS.get(tier, TIER_LABELS[TIER_BELOW])
    return arab if arabic else english


def tier_number(label_or_number) -> int:
    try:
        return int(float(label_or_number))
    except (TypeError, ValueError):
        return LABEL_TO_TIER.get(str(label_or_number).strip(), TIER_BELOW)


def load_catalog_summary() -> pd.DataFrame:
    if not EVIDENCE_SUMMARY_FILE.exists():
        return pd.DataFrame(columns=["disease_id", "rsid", "catalog_best_p_value", "catalog_gws_study_count",
                                     "catalog_study_count", "catalog_max_sample_size"])
    return pd.read_csv(EVIDENCE_SUMMARY_FILE, dtype={"disease_id": str, "rsid": str})


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _effect_magnitude(row) -> float:
    """|log(OR)| when an odds ratio is given, else |beta|; 0 when unknown."""
    odds = row.get("odds_ratio_numeric")
    beta = row.get("effect_size_numeric")
    if odds is not None and not pd.isna(odds) and odds > 0:
        return round(abs(math.log(odds)), 4)
    if beta is not None and not pd.isna(beta):
        return round(abs(float(beta)), 4)
    return 0.0


def _explain(row, arabic: bool) -> str:
    gws, total = int(row["independent_gws_studies"]), int(row["independent_studies"])
    p = row["best_p_value"]
    p_text = f"{p:.1e}" if p and not pd.isna(p) else "—"
    n = int(row["max_sample_size"] or 0)
    tier = int(row["evidence_tier"])
    if arabic:
        reason = {
            TIER_CONFIRMED: f"دلالة على مستوى الجينوم في {arabic_studies(gws)}",
            TIER_STRONG: "دلالة على مستوى الجينوم في دراسة واحدة",
            TIER_SUGGESTIVE: "دلالة مقترحة (أضعف من عتبة الجينوم)",
            TIER_BELOW: "لا تبلغ عتبة الدلالة",
        }[tier]
        size = f"، أكبر عينة {n:,}" if n else ""
        return f"{reason}. أفضل قيمة p = {p_text}، عدد الدراسات {total}{size}."
    reason = {
        TIER_CONFIRMED: f"Genome-wide significant in {gws} independent studies",
        TIER_STRONG: "Genome-wide significant in one study",
        TIER_SUGGESTIVE: "Suggestive (below genome-wide significance)",
        TIER_BELOW: "Does not reach significance",
    }[tier]
    size = f", largest sample {n:,}" if n else ""
    return f"{reason}. Best p = {p_text}, {total} studies{size}."


def assign_evidence(df: pd.DataFrame, summary: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add evidence-level columns, order rows within each disease, and drop the old score columns."""
    out = df.drop(columns=[c for c in OBSOLETE_COLUMNS if c in df.columns]).copy()
    if out.empty:
        for col in EVIDENCE_COLUMNS:
            out[col] = pd.Series(dtype=object)
        return out
    summary = load_catalog_summary() if summary is None else summary
    out["disease_id"] = out["disease_id"].astype(str)
    out["rsid"] = out["rsid"].astype(str).str.lower()
    for col in ("p_value_numeric", "odds_ratio_numeric", "effect_size_numeric"):
        out[col] = _num(out[col]) if col in out.columns else np.nan
    if out["p_value_numeric"].isna().all() and "p_value" in out.columns:
        out["p_value_numeric"] = _num(out["p_value"])

    pubmed = out["pubmed_id"].astype(str).str.strip() if "pubmed_id" in out.columns else pd.Series("", index=out.index)
    study_key = pubmed.where(pubmed.ne("") & pubmed.ne("nan"), out.get("study_title", pd.Series("", index=out.index)))
    out["_study"] = study_key.astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    out["_gws_study"] = out["_study"].where(out["p_value_numeric"] < GENOME_WIDE_P)

    from core.regions import parse_sample_groups
    text = out["ancestry"].astype(str) if "ancestry" in out.columns else pd.Series("", index=out.index)
    out["_n"] = text.map(lambda t: sum(g.count for g in parse_sample_groups(t)))

    groups = out.groupby(["disease_id", "rsid"])
    local = pd.DataFrame({
        "local_best_p": groups["p_value_numeric"].min(),
        "local_gws": groups["_gws_study"].nunique(),
        "local_studies": groups["_study"].nunique(),
        "local_n": groups["_n"].max(),
    }).reset_index()
    merged = local.merge(summary, on=["disease_id", "rsid"], how="left")
    merged["best_p_value"] = merged[["local_best_p", "catalog_best_p_value"]].min(axis=1)
    # The larger of the catalog count and the platform's own rows: rows added by an admin that are
    # already in the catalog are not counted twice (conservative for genuinely new studies).
    merged["independent_gws_studies"] = merged[["local_gws", "catalog_gws_study_count"]].max(axis=1)
    merged["independent_studies"] = merged[["local_studies", "catalog_study_count"]].max(axis=1)
    merged["max_sample_size"] = merged[["local_n", "catalog_max_sample_size"]].max(axis=1).fillna(0)
    merged = merged[["disease_id", "rsid", "best_p_value", "independent_gws_studies",
                                    "independent_studies", "max_sample_size"]]
    for col in ("independent_gws_studies", "independent_studies", "max_sample_size"):
        merged[col] = merged[col].fillna(0).astype(int)

    out = out.drop(columns=[c for c in merged.columns if c in out.columns and c not in ("disease_id", "rsid")])
    out = out.merge(merged, on=["disease_id", "rsid"], how="left")
    out["effect_magnitude"] = out.apply(_effect_magnitude, axis=1)
    out["evidence_tier"] = [tier_for(p, g) for p, g in zip(out["best_p_value"], out["independent_gws_studies"])]
    out["rank_label"] = out["evidence_tier"].map(lambda t: TIER_LABELS[t][0])
    out["rank_label_arabic"] = out["evidence_tier"].map(lambda t: TIER_LABELS[t][1])
    out["score_explanation"] = out.apply(lambda r: _explain(r, arabic=False), axis=1)
    out["score_explanation_arabic"] = out.apply(lambda r: _explain(r, arabic=True), axis=1)

    out = out.drop(columns=["_study", "_gws_study", "_n"])
    out = sort_by_evidence(out)
    out["rank_position_within_disease"] = out.groupby("disease_id").cumcount() + 1
    out["ranked_association_id"] = [f"RANKED_ASSOC_{i:06d}" for i in range(1, len(out) + 1)]
    return out


def sort_by_evidence(df: pd.DataFrame, within_disease: bool = True) -> pd.DataFrame:
    """Order by best p-value, then evidence level, effect size and sample size."""
    keys = pd.DataFrame({
        "tier": _num(df["evidence_tier"]).fillna(0),
        "p": _num(df.get("best_p_value", df.get("p_value_numeric"))).fillna(1.0),
        "row_p": _num(df.get("p_value_numeric", df.get("p_value"))).fillna(1.0),
        "effect": _num(df.get("effect_magnitude", pd.Series(0, index=df.index))).fillna(0),
        "n": _num(df.get("max_sample_size", pd.Series(0, index=df.index))).fillna(0),
    }, index=df.index)
    by, ascending = ["p", "tier", "effect", "n", "row_p"], [True, False, False, False, True]
    if within_disease and "disease_id" in df.columns:
        keys.insert(0, "disease", _num(df["disease_id"]).fillna(0))
        by, ascending = ["disease", *by], [True, *ascending]
    order = keys.sort_values(by, ascending=ascending, kind="mergesort").index
    return df.loc[order].reset_index(drop=True)
