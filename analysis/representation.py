"""
3.1  Representation of Arab and Middle Eastern populations in GWAS.

Run:  python -m analysis.representation        (writes analysis/results/ and analysis/figures/)
"""

from __future__ import annotations

import json
from collections import Counter

import pandas as pd

from analysis.catalog import catalog_name, load_studies
from core.diseases import list_diseases
from core.paths import PROJECT_ROOT
from core.regions import ancestry_groups, is_arab, is_middle_eastern, parse_sample_groups

RESULTS = PROJECT_ROOT / "analysis" / "results"
FIGURES = PROJECT_ROOT / "analysis" / "figures"
GROUP_ORDER = ["Arab", "Middle Eastern", "European", "East Asian", "South Asian", "African American", "African",
               "Hispanic / Latin American", "Other", "Multiple", "Not reported"]


def _participants(text: str) -> Counter:
    counts = Counter()
    for item in parse_sample_groups(text):
        if len(item.groups) == 1:
            counts[item.groups[0]] += item.count
        elif len(item.groups) > 1:
            counts["Multiple"] += item.count
        else:
            counts["Not reported"] += item.count
    return counts


def annotate(studies: pd.DataFrame) -> pd.DataFrame:
    s = studies.copy()
    for col in ("initial_sample", "replication_sample"):
        s[col] = s[col].fillna("")
    s["arab_discovery"] = s["initial_sample"].map(is_arab)
    s["me_discovery"] = s["initial_sample"].map(is_middle_eastern)
    s["arab_any"] = s["arab_discovery"] | s["replication_sample"].map(is_arab)
    s["me_any"] = s["me_discovery"] | s["replication_sample"].map(is_middle_eastern)
    s["european_only"] = s["initial_sample"].map(lambda t: ancestry_groups(t) == ["European"])
    s["participants"] = s["initial_sample"].map(_participants)
    s["n_total"] = s["participants"].map(lambda c: sum(c.values()))
    return s


def _share_table(studies: pd.DataFrame) -> pd.DataFrame:
    totals = Counter()
    for counts in studies["participants"]:
        totals.update(counts)
    grand = sum(totals.values()) or 1
    return pd.DataFrame([{"group": g, "participants": totals.get(g, 0),
                          "share_percent": round(100 * totals.get(g, 0) / grand, 3)} for g in GROUP_ORDER])


def _study_summary(studies: pd.DataFrame, label: str) -> dict:
    n = len(studies)
    counted = studies["participants"].map(lambda c: c.get("Arab", 0)).sum()
    me_counted = counted + studies["participants"].map(lambda c: c.get("Middle Eastern", 0)).sum()
    total = studies["n_total"].sum() or 1
    pct = (lambda k: round(100 * studies[k].sum() / n, 2) if n else 0.0)
    return {
        "scope": label,
        "studies": n,
        "studies_with_arab_discovery": int(studies["arab_discovery"].sum()),
        "pct_studies_arab_discovery": pct("arab_discovery"),
        "studies_with_me_discovery": int(studies["me_discovery"].sum()),
        "pct_studies_me_discovery": pct("me_discovery"),
        "pct_studies_arab_any_stage": pct("arab_any"),
        "pct_studies_european_only": pct("european_only"),
        "discovery_participants": int(studies["n_total"].sum()),
        "pct_participants_arab": round(100 * counted / total, 3),
        "pct_participants_arab_or_me": round(100 * me_counted / total, 3),
    }


def by_disease(studies: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for disease in list_diseases():
        mask = studies["diseases"].fillna("").str.split(";").map(lambda ds: disease.name_en in ds)
        subset = studies[mask]
        row = _study_summary(subset, disease.name_en)
        sig = subset["significant_by_disease"].fillna("").map(
            lambda s: dict(p.split("=") for p in s.split(";") if p).get(disease.name_en, "0")).astype(int)
        row["significant_associations"] = int(sig.sum())
        row["significant_from_arab_or_me_studies"] = int(sig[subset["me_discovery"]].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def by_year(studies: pd.DataFrame) -> pd.DataFrame:
    grouped = studies.dropna(subset=["year"]).groupby("year")
    return pd.DataFrame({
        "studies": grouped.size(),
        "pct_arab_discovery": grouped["arab_discovery"].mean().mul(100).round(2),
        "pct_me_discovery": grouped["me_discovery"].mean().mul(100).round(2),
        "pct_european_only": grouped["european_only"].mean().mul(100).round(2),
    }).reset_index().astype({"year": int})


def make_figures(shares: pd.DataFrame, diseases: pd.DataFrame, years: pd.DataFrame) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    navy, teal, purple, grey = "#0A2158", "#0E7C8C", "#5B3291", "#AAB4C5"
    FIGURES.mkdir(parents=True, exist_ok=True)
    written = []

    fig, ax = plt.subplots(figsize=(8, 4.5))
    data = shares[shares["participants"] > 0]
    colors = [purple if g in ("Arab", "Middle Eastern") else (navy if g == "European" else teal)
              if g not in ("Multiple", "Not reported") else grey for g in data["group"]]
    ax.barh(data["group"][::-1], data["share_percent"][::-1], color=colors[::-1])
    for y, v in enumerate(data["share_percent"][::-1]):
        ax.text(v + 0.5, y, f"{v:.2f}%", va="center", fontsize=8)
    ax.set_xlabel("Share of discovery participants (%)")
    ax.set_title("GWAS Catalog discovery participants by ancestry group")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    written += _save(fig, "fig1_participants_by_ancestry")

    fig, ax = plt.subplots(figsize=(8, 4.8))
    d = diseases.sort_values("pct_studies_me_discovery")
    ax.barh(d["scope"], d["pct_studies_me_discovery"], color=teal, label="Arab or Middle Eastern")
    ax.barh(d["scope"], d["pct_studies_arab_discovery"], color=purple, label="Arab")
    for y, (v, n) in enumerate(zip(d["pct_studies_me_discovery"], d["studies"])):
        ax.text(v + 0.3, y, f"{v:.1f}% of {n}", va="center", fontsize=8)
    ax.set_xlabel("Studies whose discovery sample includes the population (%)")
    ax.set_title("Arab / Middle Eastern participation per disease")
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    written += _save(fig, "fig2_studies_by_disease")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = years[(years["year"] >= 2007) & (years["studies"] >= 20)]
    ax.plot(y["year"], y["pct_me_discovery"], color=teal, marker="o", label="Arab or Middle Eastern")
    ax.plot(y["year"], y["pct_arab_discovery"], color=purple, marker="o", label="Arab")
    ax.set_ylabel("Studies including the population (%)")
    ax.set_title("Trend over time (discovery samples)")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    written += _save(fig, "fig3_trend_by_year")
    plt.close("all")
    return written


def _save(fig, name: str) -> list:
    paths = [FIGURES / f"{name}.png", FIGURES / f"{name}.svg"]
    fig.savefig(paths[0], dpi=200)
    fig.savefig(paths[1])
    return [p.relative_to(PROJECT_ROOT).as_posix() for p in paths]


def main() -> None:
    studies = annotate(load_studies())
    disease_studies = studies[studies["diseases"].fillna("") != ""]

    overall = [_study_summary(studies, "All GWAS Catalog studies"),
               _study_summary(disease_studies, "Studies on the 10 platform diseases")]
    shares = _share_table(studies)
    shares_platform = _share_table(disease_studies)
    diseases = by_disease(studies)
    years = by_year(studies)

    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(overall).to_csv(RESULTS / "representation_overall.csv", index=False)
    shares.to_csv(RESULTS / "representation_participants_catalog.csv", index=False)
    shares_platform.to_csv(RESULTS / "representation_participants_platform_diseases.csv", index=False)
    diseases.to_csv(RESULTS / "representation_by_disease.csv", index=False)
    years.to_csv(RESULTS / "representation_by_year.csv", index=False)
    arab_studies = studies[studies["me_discovery"]][["accession", "pubmed_id", "year", "diseases", "initial_sample"]]
    arab_studies.to_csv(RESULTS / "arab_or_middle_east_studies.csv", index=False)

    figures = make_figures(shares, diseases, years)
    summary = {"catalog_file": catalog_name(), "overall": overall, "figures": figures}
    (RESULTS / "representation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    pd.set_option("display.width", 200)
    print(pd.DataFrame(overall).T.to_string(header=False))
    print(shares.to_string(index=False))
    print(diseases[["scope", "studies", "pct_studies_arab_discovery", "pct_studies_me_discovery",
                    "pct_participants_arab_or_me", "significant_associations",
                    "significant_from_arab_or_me_studies"]].to_string(index=False))


if __name__ == "__main__":
    main()
