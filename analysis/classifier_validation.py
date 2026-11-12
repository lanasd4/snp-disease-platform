"""
3.2  Accuracy of the Arab / Middle Eastern sample classifier.

Usage
python -m analysis.classifier_validation make  --sample A --seed 11 --s3 100
python -m analysis.classifier_validation score --sample A
python -m analysis.classifier_validation second-sheet --sample B   (blind sheet for a 2nd annotator)
"""

from __future__ import annotations

import argparse
import json
import re

import numpy as np
import pandas as pd

from analysis.catalog import load_studies
from analysis.classifier_versions import ARAB_CLASSIFIERS, MIDDLE_EAST_CLASSIFIERS
from core.paths import PROJECT_ROOT

ANNOTATION_DIR = PROJECT_ROOT / "analysis" / "annotation"
RESULTS = PROJECT_ROOT / "analysis" / "results"

# Every classifier version takes part in defining stratum S1.
CLASSIFIERS = MIDDLE_EAST_CLASSIFIERS

HINT_RE = re.compile(
    r"\b(?:israel\w*|cypr\w*|armenia\w*|georgia\w*|azerbaij\w*|afghan\w*|north[ -]african?|gulf|levant\w*|"
    r"maghreb\w*|berber|amazigh|druze|bedouin|assyrian|chaldean|copt\w*|mizrahi|sephardi\w*|yemenite|kurd\w*|"
    r"mediterranean|arab\w*|persia\w*|iran\w*|turk\w*|egypt\w*|saudi\w*|middle[ -]east\w*|mena)\b",
    re.IGNORECASE,
)


def all_descriptions() -> pd.Series:
    studies = load_studies()
    texts = pd.concat([studies["initial_sample"], studies["replication_sample"]]).dropna()
    texts = texts.astype(str).str.strip()
    return pd.Series(sorted(set(texts[texts != ""])))


def strata(texts: pd.Series) -> pd.Series:
    any_positive = pd.Series(False, index=texts.index)
    for classifier in CLASSIFIERS.values():
        any_positive |= texts.map(classifier)
    hint = texts.str.contains(HINT_RE)
    return pd.Series(np.where(any_positive, "S1", np.where(hint, "S2", "S3")), index=texts.index)


def make_sheet(sample: str, seed: int, s3_size: int, exclude: set) -> pd.DataFrame:
    texts = all_descriptions()
    labels = strata(texts)
    frame = pd.DataFrame({"text": texts, "stratum": labels})
    sizes = frame["stratum"].value_counts().to_dict()

    pool_s3 = frame[(frame["stratum"] == "S3") & ~frame["text"].isin(exclude)]
    picked = pd.concat([
        frame[frame["stratum"] == "S1"],
        frame[frame["stratum"] == "S2"],
        pool_s3.sample(n=min(s3_size, len(pool_s3)), random_state=seed),
    ]).sample(frac=1, random_state=seed).reset_index(drop=True)  # shuffle so annotators do not see strata order

    picked.insert(0, "item_id", [f"{sample}{i + 1:04d}" for i in range(len(picked))])
    picked["gold_me"] = ""
    picked["gold_arab"] = ""
    picked["annotator2_me"] = ""
    picked["notes"] = ""
    ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)
    picked.to_csv(ANNOTATION_DIR / f"sample_{sample}.csv", index=False, encoding="utf-8-sig")
    (ANNOTATION_DIR / f"sample_{sample}_strata.json").write_text(json.dumps(
        {"population_sizes": sizes, "seed": seed, "s3_sample_size": int(min(s3_size, len(pool_s3)))}, indent=2))
    return picked


def _weighted_rates(df: pd.DataFrame, pred: str, gold: str, pop_sizes: dict) -> dict:
    tp = fp = fn = tn = 0.0
    for stratum, group in df.groupby("stratum"):
        weight = pop_sizes[stratum] / len(group)
        p, g = group[pred].astype(bool), group[gold].astype(bool)
        tp += weight * (p & g).sum()
        fp += weight * (p & ~g).sum()
        fn += weight * (~p & g).sum()
        tn += weight * (~p & ~g).sum()
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else float("nan")
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _bootstrap(df: pd.DataFrame, pred: str, gold: str, pop_sizes: dict, reps: int = 2000, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    groups = {s: g for s, g in df.groupby("stratum")}
    samples = {"precision": [], "recall": [], "f1": []}
    for _ in range(reps):
        boot = pd.concat([g.iloc[rng.integers(0, len(g), len(g))] for g in groups.values()])
        rates = _weighted_rates(boot, pred, gold, pop_sizes)
        for key in samples:
            samples[key].append(rates[key])
    return {key: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))) for key, v in samples.items()}


def cohen_kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(int), b.astype(int)
    observed = (a == b).mean()
    expected = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return float((observed - expected) / (1 - expected)) if expected < 1 else float("nan")


def _metrics_row(sheet, sample, target, name, pred_col, gold_col, pop_sizes) -> dict:
    point = _weighted_rates(sheet, pred_col, gold_col, pop_sizes)
    ci = _bootstrap(sheet, pred_col, gold_col, pop_sizes)
    return {"sample": sample, "target": target, "classifier": name, "annotated_items": len(sheet),
            **{k: round(point[k], 4) for k in ("precision", "recall", "f1")},
            "precision_ci": [round(x, 4) for x in ci["precision"]],
            "recall_ci": [round(x, 4) for x in ci["recall"]],
            "f1_ci": [round(x, 4) for x in ci["f1"]],
            "false_positives": int(round(point["fp"])), "false_negatives": int(round(point["fn"])),
            "est_positives_in_population": round(point["tp"] + point["fn"], 1)}


def score(sample: str) -> pd.DataFrame:
    sheet = pd.read_csv(ANNOTATION_DIR / f"sample_{sample}.csv", dtype=str, encoding="utf-8-sig").fillna("")
    meta = json.loads((ANNOTATION_DIR / f"sample_{sample}_strata.json").read_text())
    if (sheet["gold_me"] == "").any():
        raise SystemExit(f"{(sheet['gold_me'] == '').sum()} items in sample {sample} are not annotated yet.")
    sheet["gold"] = sheet["gold_me"].astype(int)
    sheet["gold_arab_int"] = sheet["gold_arab"].replace("", "0").astype(int)
    pop = meta["population_sizes"]

    rows, errors = [], []
    for target, classifiers, gold_col in (("Arab or Middle Eastern", MIDDLE_EAST_CLASSIFIERS, "gold"),
                                          ("Arab only", ARAB_CLASSIFIERS, "gold_arab_int")):
        for name, classifier in classifiers.items():
            pred_col = f"pred_{target}_{name}"
            sheet[pred_col] = sheet["text"].map(classifier)
            rows.append(_metrics_row(sheet, sample, target, name, pred_col, gold_col, pop))
            wrong = sheet[sheet[pred_col] != sheet[gold_col].astype(bool)]
            errors += [{"target": target, "classifier": name, "item_id": r["item_id"], "stratum": r["stratum"],
                        "predicted": bool(r[pred_col]), "gold": int(r[gold_col]), "text": r["text"],
                        "notes": r["notes"]} for _, r in wrong.iterrows()]

    second = sheet["annotator2_me"]
    if (second != "").any():
        both = sheet[second != ""]
        kappa = round(cohen_kappa(both["gold_me"], both["annotator2_me"]), 4)
        for row in rows:
            row["kappa_annotators"], row["kappa_items"] = kappa, len(both)

    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(errors).to_csv(RESULTS / f"classifier_errors_sample_{sample}.csv", index=False, encoding="utf-8-sig")
    result = pd.DataFrame(rows)
    result.to_csv(RESULTS / f"classifier_validation_sample_{sample}.csv", index=False)
    return result


SECOND_ANNOTATOR_ITEMS = 100


def make_second_annotator_sheet(sample: str, seed: int = 101) -> pd.DataFrame:
    """Blind sheet (text only) for an independent second annotator, balanced positives / negatives."""
    sheet = pd.read_csv(ANNOTATION_DIR / f"sample_{sample}.csv", dtype=str, encoding="utf-8-sig").fillna("")
    positives = sheet[sheet["gold_me"] == "1"].sample(n=SECOND_ANNOTATOR_ITEMS // 2, random_state=seed)
    negatives = sheet[sheet["gold_me"] == "0"].sample(n=SECOND_ANNOTATOR_ITEMS // 2, random_state=seed)
    blind = pd.concat([positives, negatives]).sample(frac=1, random_state=seed)[["item_id", "text"]]
    blind["annotator2_me"] = ""
    blind.to_csv(ANNOTATION_DIR / f"second_annotator_{sample}.csv", index=False, encoding="utf-8-sig")
    return blind


def merge_second_annotator(sample: str) -> int:
    """Copy the filled second-annotator labels into the sample sheet (used by `score` for kappa)."""
    filled = pd.read_csv(ANNOTATION_DIR / f"second_annotator_{sample}.csv", dtype=str, encoding="utf-8-sig").fillna("")
    filled = filled[filled["annotator2_me"].isin(["0", "1"])]
    path = ANNOTATION_DIR / f"sample_{sample}.csv"
    sheet = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    labels = filled.set_index("item_id")["annotator2_me"]
    sheet["annotator2_me"] = sheet["item_id"].map(labels).fillna(sheet["annotator2_me"])
    sheet.to_csv(path, index=False, encoding="utf-8-sig")
    return len(filled)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("action", choices=["make", "score", "second-sheet", "merge-second"])
    parser.add_argument("--sample", default="A")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--s3", type=int, default=100)
    parser.add_argument("--exclude", nargs="*", default=[], help="earlier samples whose S3 items must not repeat")
    args = parser.parse_args()

    if args.action == "make":
        exclude = set()
        for previous in args.exclude:
            exclude |= set(pd.read_csv(ANNOTATION_DIR / f"sample_{previous}.csv", encoding="utf-8-sig")["text"])
        sheet = make_sheet(args.sample, args.seed, args.s3, exclude)
        print(sheet["stratum"].value_counts().to_dict(), "->", ANNOTATION_DIR / f"sample_{args.sample}.csv")
    elif args.action == "second-sheet":
        print(len(make_second_annotator_sheet(args.sample)), "items ->",
              ANNOTATION_DIR / f"second_annotator_{args.sample}.csv")
    elif args.action == "merge-second":
        print(merge_second_annotator(args.sample), "second-annotator labels merged")
    else:
        pd.set_option("display.width", 220)
        print(score(args.sample).to_string(index=False))


if __name__ == "__main__":
    main()
