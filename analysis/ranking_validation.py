"""
3.3  Does the platform's importance score put established disease genes first?

Run:  python -m analysis.ranking_validation
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from core.diseases import list_diseases
from core.paths import PROJECT_ROOT, RANKED_ASSOCIATIONS_FILE

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


def load_variants() -> pd.DataFrame:
    df = pd.read_csv(RANKED_ASSOCIATIONS_FILE, dtype=str)
    df["score"] = pd.to_numeric(df["importance_score"], errors="coerce").fillna(0)
    df["p"] = pd.to_numeric(df["p_value"], errors="coerce")
    df["neglog10p"] = -np.log10(df["p"].clip(lower=1e-320))
    df = df.sort_values(["score", "p"], ascending=[False, True])
    return df.drop_duplicates(subset=["disease_name", "rsid"]).reset_index(drop=True)


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
        for name, col in (("score", "score"), ("pvalue_only", "neglog10p")):
            values = d[col].to_numpy()
            row[f"auc_{name}"] = round(auc(values, labels), 4)
            lo, hi = bootstrap_ci(values, labels, rng) if labels.sum() and (~labels).sum() else (np.nan, np.nan)
            row[f"auc_{name}_ci"] = [round(lo, 4), round(hi, 4)]
        ordered = d.sort_values(["score", "neglog10p"], ascending=False)
        for k in TOP_K:
            top = ordered.head(k)
            row[f"precision_at_{k}"] = round(top["is_reference"].mean(), 4)
            found = [gene for gene, names in genes if top["gene_symbol"].map(lambda g: bool(gene_tokens(g) & names)).any()]
            row[f"gene_recall_at_{k}"] = round(len(found) / len(present), 4) if present else float("nan")
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


def make_figure(table: pd.DataFrame) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    t = table.sort_values("auc_score")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    y = np.arange(len(t))
    lo = [c[0] for c in t["auc_score_ci"]]
    hi = [c[1] for c in t["auc_score_ci"]]
    ax.errorbar(t["auc_score"], y, xerr=[t["auc_score"] - lo, np.array(hi) - t["auc_score"]], fmt="o",
                color="#0E7C8C", label="Importance score", capsize=3)
    ax.scatter(t["auc_pvalue_only"], y + 0.18, marker="s", color="#5B3291", label="p-value only")
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

    pooled = {"importance_score": pooled_permutation(variants, "score", rng),
              "pvalue_only": pooled_permutation(variants, "neglog10p", rng)}

    RESULTS.mkdir(parents=True, exist_ok=True)
    table.to_csv(RESULTS / "ranking_validation_by_disease.csv", index=False)
    variants[variants["is_reference"].astype(bool)][["disease_name", "rsid", "gene_symbol", "score", "p_value"]] \
        .to_csv(RESULTS / "ranking_validation_reference_variants.csv", index=False)
    figures = make_figure(table)
    (RESULTS / "ranking_validation_summary.json").write_text(
        json.dumps({"pooled": pooled, "figures": figures}, indent=2), encoding="utf-8")

    pd.set_option("display.width", 230)
    print(table.drop(columns=["auc_score_ci", "auc_pvalue_only_ci"]).to_string(index=False))
    print(json.dumps(pooled, indent=2))


if __name__ == "__main__":
    main()
