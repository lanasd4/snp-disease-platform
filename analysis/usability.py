"""
3.4  Usability study analysis (System Usability Scale + task success).

Run:  python -m analysis.usability            (writes analysis/results/usability_summary.json)
"""

from __future__ import annotations

import argparse
import json
import math

import pandas as pd

from core.paths import PROJECT_ROOT

STUDY_DIR = PROJECT_ROOT / "analysis" / "usability"
RESPONSES = STUDY_DIR / "responses.csv"
RESULTS = PROJECT_ROOT / "analysis" / "results"
SUS_ITEMS = [f"sus_{i}" for i in range(1, 11)]
TASKS = [f"task_{i}" for i in range(1, 6)]
TIMES = [f"time_{i}" for i in range(1, 6)]
SUS_BENCHMARK = 68.0
# Two-sided 95% t critical values for small samples (df -> t).
T_CRIT = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
          12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def sus_score(answers) -> float:
    """SUS score (0-100) from ten answers on a 1-5 scale."""
    values = [int(a) for a in answers]
    if len(values) != 10 or any(v < 1 or v > 5 for v in values):
        raise ValueError("SUS needs ten answers between 1 and 5.")
    total = sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(values))
    return total * 2.5


def _t_crit(df: int) -> float:
    keys = sorted(T_CRIT)
    for k in keys:
        if df <= k:
            return T_CRIT[k]
    return 1.96


def mean_ci(values) -> dict:
    s = pd.Series(values, dtype=float).dropna()
    n = len(s)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None, "sd": None}
    if n == 1:
        return {"n": 1, "mean": round(float(s.iloc[0]), 2), "ci95": None, "sd": None}
    half = _t_crit(n - 1) * s.std(ddof=1) / math.sqrt(n)
    return {"n": n, "mean": round(float(s.mean()), 2), "sd": round(float(s.std(ddof=1)), 2),
            "ci95": [round(float(s.mean() - half), 2), round(float(s.mean() + half), 2)]}


def wilson(successes: int, n: int) -> list:
    if n == 0:
        return [None, None]
    z, p = 1.96, successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 3), round(centre + half, 3)]


def analyse(responses: pd.DataFrame) -> dict:
    df = responses.copy()
    df["sus"] = df[SUS_ITEMS].apply(sus_score, axis=1)
    summary = {
        "participants": len(df),
        "sus": mean_ci(df["sus"]),
        "sus_above_benchmark_share": round(float((df["sus"] > SUS_BENCHMARK).mean()), 3) if len(df) else None,
        "tasks": {},
        "by_group": {},
    }
    for task, time in zip(TASKS, TIMES):
        done = pd.to_numeric(df[task], errors="coerce").dropna()
        summary["tasks"][task] = {
            "completion_rate": round(float(done.mean()), 3) if len(done) else None,
            "completion_ci95": wilson(int(done.sum()), len(done)),
            "median_seconds": float(pd.to_numeric(df[time], errors="coerce").median())
            if time in df and pd.to_numeric(df[time], errors="coerce").notna().any() else None,
        }
    if "group" in df:
        for group, g in df.groupby("group"):
            summary["by_group"][str(group)] = mean_ci(g["sus"])
    return summary


def write_template() -> None:
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["participant_id", "group", "language", *SUS_ITEMS, *TASKS, *TIMES, "comments"]
    pd.DataFrame(columns=columns).to_csv(STUDY_DIR / "responses_template.csv", index=False, encoding="utf-8-sig")
    print("template ->", STUDY_DIR / "responses_template.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="SUS / task-success analysis")
    parser.add_argument("action", nargs="?", default="analyse", choices=["analyse", "template"])
    args = parser.parse_args()
    if args.action == "template":
        write_template()
        return
    if not RESPONSES.exists():
        raise SystemExit(f"No responses yet: fill {RESPONSES} (copy responses_template.csv).")
    summary = analyse(pd.read_csv(RESPONSES, encoding="utf-8-sig"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "usability_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                                     encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
