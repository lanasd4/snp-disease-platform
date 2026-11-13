"""
3.3  Do the platform's evidence levels put established disease genes first?

Compares, per disease, how well each ordering ranks variants in established
genes above the rest: the evidence levels (current platform order), the former
weighted importance score (frozen in analysis.legacy_ranking), replication count
alone, and p-value alone.

Run:  python -m analysis.ranking_validation
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from analysis.legacy_ranking import legacy_importance_score
from core.diseases import list_diseases
from core.paths import PROCESSED_DATA_DIR, PROJECT_ROOT, RANKED_ASSOCIATIONS_FILE

REFERENCE_FILE = PROJECT_ROOT / "analysis" / "reference" / "established_loci.csv"
RESULTS = PROJECT_ROOT / "analysis" / "results"
FIGURES = PROJECT_ROOT / "analysis" / "figures"
TOP_K = (10, 20)
BOOTSTRAP = 2000
PERMUTATIONS = 5000
RNG_SEED = 2026


def gene_tokens(field) -> set:
    return {g.strip().upper() for g in re.split(r"\s+-\s+|[,;/]", str(field or "")) if g.strip()}


def load_reference() -> dict:
    ref = pd.read_csv(REFERENCE_FILE, dtype=str).fillna("")
    out: dict = {}
    for row in ref.itertuples():
        names = {row.gene.upper(), *(a.strip().upper() for a in row.aliases.split(";") if a.strip())}
        out.setdefault(row.disease, []).append((row.gene, names))
    return out


METHODS = {  # column -> label
    "evidence": "Evidence levels (platform)",
    "legacy_score": "Former importance score",
    "replication": "Replication count only",
    "neglog10p": "p-value only",
}


def load_variants() -> pd.DataFrame:
    """One row per disease-variant pair, with a value per ordering method (higher = ranked first)."""
    df = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    features = pd.read_csv(PROCESSED_DATA_DIR / "ranking_features.csv", dtype=str)
    legacy = legacy_importance_score(features)[["ranking_feature_id", "importance_score"]]
    df = df.merge(legacy, on="ranking_feature_id", how="left")
    df["legacy_score"] = pd.to_numeric(df["importance_score"], errors="coerce").fillna(0)
    df["p"] = pd.to_numeric(df["p_value"], errors="coerce")
    df["position"] = pd.to_numeric(df["rank_position_within_disease"], errors="coerce")
    df = df.sort_values(["disease_name", "position"])  # the platform's own order
    pairs = df.groupby(["disease_name", "rsid"], sort=False)
    out = pairs.first().reset_index()
    out["p"] = pairs["p"].min().values
    out["legacy_score"] = pairs["legacy_score"].max().values
    out["neglog10p"] = -np.log10(out["p"].clip(lower=1e-320))
    out["replication"] = pd.to_numeric(out["independent_gws_studies"], errors="coerce").fillna(0)
    out["evidence"] = -out["position"]
    return out.reset_index(drop=True)


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney AUC with ties counted as 1/2."""
    pos, neg = scores[labels], scores[~labels]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def bootstrap_ci(scores, labels, rng) -> tuple:
    n = len(scores)
    values = []
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, n, n)
        values.append(auc(scores[idx], labels[idx]))
    return tuple(float(x) for x in np.nanpercentile(values, [2.5, 97.5]))


def per_disease(variants: pd.DataFrame, reference: dict, rng) -> pd.DataFrame:
    rows = []
    for disease in list_diseases():
        d = variants[variants["disease_name"] == disease.name_en].copy()
        genes = reference.get(disease.name_en, [])
        all_names = set().union(*(names for _, names in genes)) if genes else set()
        d["is_reference"] = d["gene_symbol"].map(lambda g: bool(gene_tokens(g) & all_names))
        labels = d["is_reference"].to_numpy()
        present = [gene for gene, names in genes if d["gene_symbol"].map(lambda g: bool(gene_tokens(g) & names)).any()]

        row = {"disease": disease.name_en, "variants": len(d), "reference_variants": int(labels.sum()),
               "reference_genes_listed": len(genes), "reference_genes_in_data": len(present),
               "base_rate": round(labels.mean(), 4) if len(d) else float("nan")}
        for col in METHODS:
            values = d[col].to_numpy()
            row[f"auc_{col}"] = round(auc(values, labels), 4)
            lo, hi = bootstrap_ci(values, labels, rng) if labels.sum() and (~labels).sum() else (np.nan, np.nan)
            row[f"auc_{col}_ci"] = [round(lo, 4), round(hi, 4)]
        for col in ("evidence", "legacy_score"):
            ordered = d.sort_values([col, "neglog10p"], ascending=False)
            for k in TOP_K:
                top = ordered.head(k)
                row[f"precision_at_{k}_{col}"] = round(top["is_reference"].mean(), 4)
                found = [gene for gene, names in genes
                         if top["gene_symbol"].map(lambda g: bool(gene_tokens(g) & names)).any()]
                row[f"gene_recall_at_{k}_{col}"] = round(len(found) / len(present), 4) if present else float("nan")
        rows.append(row)
        variants.loc[d.index, "is_reference"] = d["is_reference"]
    return pd.DataFrame(rows)


def pooled_permutation(variants: pd.DataFrame, column: str, rng) -> dict:
    """Mean per-disease AUC and its stratified permutation p-value."""
    groups = [(g[column].to_numpy(), g["is_reference"].astype(bool).to_numpy())
              for _, g in variants.groupby("disease_name") if g["is_reference"].astype(bool).any()]
    observed = float(np.mean([auc(s, lab) for s, lab in groups]))
    null = []
    for _ in range(PERMUTATIONS):
        null.append(np.mean([auc(rng.permutation(s), lab) for s, lab in groups]))
    p = (1 + sum(v >= observed for v in null)) / (1 + PERMUTATIONS)
    return {"mean_auc": round(observed, 4), "permutation_p": round(float(p), 5), "diseases": len(groups)}


def paired_difference(variants: pd.DataFrame, new: str, old: str, rng) -> dict:
    """Mean per-disease AUC difference (new - old) with a stratified bootstrap 95% CI."""
    groups = [(g[new].to_numpy(), g[old].to_numpy(), g["is_reference"].astype(bool).to_numpy())
              for _, g in variants.groupby("disease_name") if g["is_reference"].astype(bool).any()]
    diffs = [auc(a, lab) - auc(b, lab) for a, b, lab in groups]
    boot = []
    for _ in range(BOOTSTRAP):
        sample = []
        for a, b, lab in groups:
            idx = rng.integers(0, len(lab), len(lab))
            sample.append(auc(a[idx], lab[idx]) - auc(b[idx], lab[idx]))
        boot.append(np.nanmean(sample))
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return {"mean_difference": round(float(np.mean(diffs)), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "diseases_improved": int(sum(d > 0 for d in diffs)), "diseases": len(diffs)}


def make_figure(table: pd.DataFrame) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    t = table.sort_values("auc_evidence")
    fig, ax = plt.subplots(figsize=(8, 5.2))
    y = np.arange(len(t))
    lo = [c[0] for c in t["auc_evidence_ci"]]
    hi = [c[1] for c in t["auc_evidence_ci"]]
    ax.errorbar(t["auc_evidence"], y, xerr=[t["auc_evidence"] - lo, np.array(hi) - t["auc_evidence"]], fmt="o",
                color="#0A2158", label=METHODS["evidence"], capsize=3, zorder=3)
    ax.scatter(t["auc_legacy_score"], y + 0.2, marker="x", color="#C98A12", label=METHODS["legacy_score"])
    ax.scatter(t["auc_neglog10p"], y - 0.2, marker="s", color="#5B3291", label=METHODS["neglog10p"], s=18)
    ax.axvline(0.5, color="#AAB4C5", linestyle="--", linewidth=1)
    ax.set_yticks(y, t["disease"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("AUC: established genes ranked above other variants")
    ax.set_title("Ranking of established disease genes")
    ax.legend(frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    paths = [FIGURES / "fig4_ranking_validation.png", FIGURES / "fig4_ranking_validation.svg"]
    fig.savefig(paths[0], dpi=200)
    fig.savefig(paths[1])
    plt.close(fig)
    return [p.relative_to(PROJECT_ROOT).as_posix() for p in paths]


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    reference = load_reference()
    variants = load_variants()
    variants["is_reference"] = False
    table = per_disease(variants, reference, rng)

    pooled = {col: pooled_permutation(variants, col, rng) for col in METHODS}
    pooled["evidence_vs_legacy"] = paired_difference(variants, "evidence", "legacy_score", rng)

    RESULTS.mkdir(parents=True, exist_ok=True)
    table.to_csv(RESULTS / "ranking_validation_by_disease.csv", index=False)
    variants[variants["is_reference"].astype(bool)][["disease_name", "rsid", "gene_symbol", "rank_label",
                                                     "independent_gws_studies", "legacy_score", "p"]] \
        .to_csv(RESULTS / "ranking_validation_reference_variants.csv", index=False)
    figures = make_figure(table)
    (RESULTS / "ranking_validation_summary.json").write_text(
        json.dumps({"pooled": pooled, "figures": figures}, indent=2), encoding="utf-8")

    pd.set_option("display.width", 230)
    print(table[["disease", "variants", "reference_variants"] + [f"auc_{c}" for c in METHODS]].to_string(index=False))
    print(json.dumps(pooled, indent=2))


if __name__ == "__main__":
    main()
