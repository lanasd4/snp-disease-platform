"""
3.5  Learning study: pre/post knowledge test for biology students.

Two parallel forms (A, B) of a ten-question test are used before and after a
guided session with the platform; half of the participants take A then B, the
other half B then A. This module holds the scoring and the analysis.

Run:  python -m analysis.learning template      empty responses file
      python -m analysis.learning merge ...     build responses from four Google Forms exports
      python -m analysis.learning analyse       learning gain (writes analysis/results/learning_summary.json)
      python -m analysis.learning instrument    printable forms + answer key (analysis/learning/instrument.md)
      python -m analysis.learning script        Google Apps Script that creates the four forms
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from analysis.usability import mean_ci
from core.paths import PROJECT_ROOT

STUDY_DIR = PROJECT_ROOT / "analysis" / "learning"
ITEMS_FILE = STUDY_DIR / "items.json"
RESPONSES = STUDY_DIR / "responses.csv"
RESULTS = PROJECT_ROOT / "analysis" / "results"
LETTERS = "abcd"
ARABIC_LETTERS = "أبجد"
N_ITEMS = 10
N_CONF = 4
N_USE = 5
N_OPEN = 3
BOOTSTRAP = 5000
RNG_SEED = 2026


def load_items() -> dict:
    return json.loads(ITEMS_FILE.read_text(encoding="utf-8"))


# --- scoring -----------------------------------------------------------------------

def answer_index(item: dict, value) -> Optional[int]:
    """Index of the chosen option from a letter (a-d / أ-د), a 1-4 number, or the option's text."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 1:
        if text.lower() in LETTERS:
            return LETTERS.index(text.lower())
        if text in ARABIC_LETTERS:
            return ARABIC_LETTERS.index(text)
        if text in "1234":
            return int(text) - 1
    for i, option in enumerate(item["options"]):
        if text == option.strip():
            return i
    return None


def score_answers(form: list, answers) -> list:
    """1 for each correct answer, 0 for wrong or missing."""
    return [int(answer_index(item, value) == item["correct"]) for item, value in zip(form, answers)]


# --- analysis ----------------------------------------------------------------------

def _number(x):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, 4)


def _paired_tests(pre: np.ndarray, post: np.ndarray) -> dict:
    from scipy import stats

    diff = post - pre
    out = {"n": int(len(diff)), "mean_gain": _number(diff.mean()) if len(diff) else None,
           "paired_t_p": None, "wilcoxon_p": None, "cohen_dz": None}
    if len(diff) < 2:
        return out
    sd = diff.std(ddof=1)
    out["cohen_dz"] = _number(diff.mean() / sd) if sd > 0 else None
    if sd > 0:
        out["paired_t_p"] = _number(stats.ttest_rel(post, pre).pvalue)
    if np.any(diff != 0):
        try:
            out["wilcoxon_p"] = _number(stats.wilcoxon(post, pre, zero_method="wilcox").pvalue)
        except ValueError:
            pass
    return out


def _bootstrap_ci(values: np.ndarray) -> Optional[list]:
    if len(values) < 2:
        return None
    rng = np.random.default_rng(RNG_SEED)
    means = [values[rng.integers(0, len(values), len(values))].mean() for _ in range(BOOTSTRAP)]
    return [_number(v) for v in np.percentile(means, [2.5, 97.5])]


def participant_scores(responses: pd.DataFrame, items: dict) -> pd.DataFrame:
    """Per participant: pre and post totals and per-item correctness."""
    rows = []
    for _, r in responses.iterrows():
        row = {"participant_id": r["participant_id"], "form_pre": r["form_pre"], "form_post": r["form_post"],
               "major": r.get("major", ""), "year": r.get("year", "")}
        for stage, form_col in (("pre", "form_pre"), ("post", "form_post")):
            form = items["forms"][str(r[form_col]).strip().upper()]
            marks = score_answers(form, [r.get(f"{stage}_q{i}") for i in range(1, N_ITEMS + 1)])
            row[stage] = sum(marks)
            for i, mark in enumerate(marks, 1):
                row[f"{stage}_item{i}"] = mark
        rows.append(row)
    return pd.DataFrame(rows)


def analyse(responses: pd.DataFrame, items: Optional[dict] = None) -> dict:
    items = items or load_items()
    scores = participant_scores(responses, items)
    pre, post = scores["pre"].to_numpy(float), scores["post"].to_numpy(float)
    gain = post - pre

    summary = {
        "participants": int(len(scores)),
        "max_score": N_ITEMS,
        "pre": mean_ci(pre),
        "post": mean_ci(post),
        "gain": {**mean_ci(gain), "bootstrap_ci95": _bootstrap_ci(gain),
                 "improved": int((gain > 0).sum()), "unchanged": int((gain == 0).sum()),
                 "declined": int((gain < 0).sum())},
        "tests": _paired_tests(pre, post),
    }
    # Normalised gain (Hake): share of the possible improvement that was achieved.
    summary["normalised_gain"] = _number((post.mean() - pre.mean()) / (N_ITEMS - pre.mean())) \
        if len(scores) and pre.mean() < N_ITEMS else None

    # Order check: parallel forms should give the same picture whichever came first.
    summary["by_order"] = {}
    for order, g in scores.groupby(scores["form_pre"].str.upper() + "->" + scores["form_post"].str.upper()):
        summary["by_order"][order] = {"n": int(len(g)), "pre": _number(g["pre"].mean()),
                                      "post": _number(g["post"].mean()), "gain": _number((g["post"] - g["pre"]).mean())}
    form_scores = {"A": [], "B": []}
    for stage in ("pre", "post"):
        for _, r in scores.iterrows():
            form_scores[str(r[f"form_{stage}"]).upper()].append(r[stage])
    summary["form_means"] = {k: _number(np.mean(v)) if v else None for k, v in form_scores.items()}

    # Per concept: percentage correct before and after (items of the same concept in both forms).
    summary["by_concept"] = {}
    for position, concept in enumerate(items["concepts"], 1):
        pre_marks = scores[f"pre_item{position}"].to_numpy(float)
        post_marks = scores[f"post_item{position}"].to_numpy(float)
        summary["by_concept"][concept] = {"pre_pct": _number(pre_marks.mean() * 100),
                                          "post_pct": _number(post_marks.mean() * 100),
                                          "change_pct_points": _number((post_marks - pre_marks).mean() * 100)}

    # Self-rated confidence (1-5) before and after.
    conf = {}
    for i in range(1, N_CONF + 1):
        a = pd.to_numeric(responses.get(f"pre_c{i}"), errors="coerce")
        b = pd.to_numeric(responses.get(f"post_c{i}"), errors="coerce")
        ok = a.notna() & b.notna()
        conf[f"c{i}"] = {"pre": _number(a[ok].mean()) if ok.any() else None,
                         "post": _number(b[ok].mean()) if ok.any() else None,
                         **(_paired_tests(a[ok].to_numpy(float), b[ok].to_numpy(float)) if ok.sum() else {})}
    summary["confidence"] = conf

    # Perceived usefulness (post only, 1-5): mean and share who agree (4 or 5).
    use = {}
    for i in range(1, N_USE + 1):
        v = pd.to_numeric(responses.get(f"u{i}"), errors="coerce").dropna()
        use[f"u{i}"] = {"mean": _number(v.mean()) if len(v) else None,
                        "agree_share": _number((v >= 4).mean()) if len(v) else None, "n": int(len(v))}
    summary["usefulness"] = use

    summary["by_major"] = {}
    for major, g in scores.groupby(scores["major"].replace("", "unknown")):
        summary["by_major"][str(major)] = {"n": int(len(g)), "mean_gain": _number((g["post"] - g["pre"]).mean())}
    return summary


# --- Google Forms exports -> one responses file ------------------------------------

def _tidy(df: pd.DataFrame, expected: int, name: str) -> pd.DataFrame:
    if df.shape[1] < expected:
        raise ValueError(f"{name}: expected at least {expected} columns, found {df.shape[1]}.")
    df = df.iloc[:, :expected].copy()
    df.iloc[:, 1] = df.iloc[:, 1].astype(str).str.strip().str.upper()
    return df


def merge_exports(pre_a: pd.DataFrame, pre_b: pd.DataFrame, post_a: pd.DataFrame, post_b: pd.DataFrame) -> pd.DataFrame:
    """Join the pre and post exports on the participant code.

    Column order is fixed by the Apps Script:
      pre : timestamp, code, major, year, prior_gwas, Q1..Q10, c1..c4
      post: timestamp, code, Q1..Q10, c1..c4, u1..u5, open1..open3
    """
    pre_cols = ["timestamp", "participant_id", "major", "year", "prior_gwas",
                *[f"pre_q{i}" for i in range(1, N_ITEMS + 1)], *[f"pre_c{i}" for i in range(1, N_CONF + 1)]]
    post_cols = ["timestamp", "participant_id", *[f"post_q{i}" for i in range(1, N_ITEMS + 1)],
                 *[f"post_c{i}" for i in range(1, N_CONF + 1)], *[f"u{i}" for i in range(1, N_USE + 1)],
                 *[f"open{i}" for i in range(1, N_OPEN + 1)]]
    pre_parts, post_parts = [], []
    for code, df in (("A", pre_a), ("B", pre_b)):
        t = _tidy(df, len(pre_cols), f"pre {code}")
        t.columns = pre_cols
        t["form_pre"] = code
        pre_parts.append(t)
    for code, df in (("A", post_a), ("B", post_b)):
        t = _tidy(df, len(post_cols), f"post {code}")
        t.columns = post_cols
        t["form_post"] = code
        post_parts.append(t)
    pre = pd.concat(pre_parts).drop_duplicates("participant_id", keep="last")
    post = pd.concat(post_parts).drop_duplicates("participant_id", keep="last")
    merged = pre.drop(columns="timestamp").merge(post.drop(columns="timestamp"), on="participant_id", how="inner")
    merged["comments"] = merged[[f"open{i}" for i in range(1, N_OPEN + 1)]].fillna("").astype(str).agg(" | ".join, axis=1)
    merged = merged.drop(columns=[f"open{i}" for i in range(1, N_OPEN + 1)])
    return merged


def response_columns() -> list:
    return ["participant_id", "form_pre", "form_post", "major", "year", "prior_gwas",
            *[f"pre_q{i}" for i in range(1, N_ITEMS + 1)], *[f"post_q{i}" for i in range(1, N_ITEMS + 1)],
            *[f"pre_c{i}" for i in range(1, N_CONF + 1)], *[f"post_c{i}" for i in range(1, N_CONF + 1)],
            *[f"u{i}" for i in range(1, N_USE + 1)], "comments"]


# --- printable instrument and Google Forms script ----------------------------------

def instrument_markdown(items: Optional[dict] = None) -> str:
    items = items or load_items()
    lines = ["# أداة القياس: اختبار الفهم القبلي والبعدي", "",
             f"> الإصدار: {items['version']}", "",
             "> **للباحثة فقط:** هذا الملف يحوي مفتاح الإجابات. لا تعطيه للمشاركين.", ""]
    for code, form in items["forms"].items():
        lines += [f"## النسخة {code}", ""]
        for i, item in enumerate(form, 1):
            lines.append(f"**س{i}.** {item['text']}")
            if item.get("card"):
                lines += ["", "```", item["card"].replace("\n", "\n"), "```", "", f"**{item['question']}**"]
            lines.append("")
            for letter, option in zip(ARABIC_LETTERS, item["options"]):
                lines.append(f"- {letter}) {option}")
            lines.append("")
        lines += ["### درجة الثقة (1 = غير واثق إطلاقًا، 5 = واثق جدًا)", ""]
        lines += [f"{i}. {t}" for i, t in enumerate(items["confidence"], 1)]
        lines.append("")
    lines += ["## مفتاح الإجابات (للباحثة فقط)", "", "| السؤال | المفهوم | النسخة A | النسخة B |", "|---|---|---|---|"]
    for i, concept in enumerate(items["concepts"]):
        a, b = items["forms"]["A"][i]["correct"], items["forms"]["B"][i]["correct"]
        lines.append(f"| س{i + 1} | {concept} | {ARABIC_LETTERS[a]} | {ARABIC_LETTERS[b]} |")
    lines += ["", "## أسئلة ما بعد الجلسة فقط", "", "**مدى الموافقة (1 = لا أوافق بشدة، 5 = أوافق بشدة):**", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(items["usefulness"], 1)]
    lines += ["", "**أسئلة مفتوحة:**", ""] + [f"- {q}" for q in items["open_questions"]]
    return "\n".join(lines) + "\n"


APPS_SCRIPT = r"""/**
 * Creates the four Google Forms of the learning study: Pre A, Pre B, Post A, Post B.
 * 1) Open https://script.google.com and create a new project.
 * 2) Paste this whole file, save, choose the function createLearningForms and press Run.
 * 3) Authorise when asked, then open View > Logs: the links to the four forms are listed there.
 * Participants take A then B, or B then A (alternate between the two orders).
 * The forms are not quizzes, so participants never see the correct answers; scoring is done by
 * analysis/learning.py from the exported answers.
 */
const DATA = __DATA__;

function createLearningForms() {
  const lines = [];
  ['pre', 'post'].forEach(stage => {
    ['A', 'B'].forEach(code => {
      const form = buildForm(stage, code);
      lines.push(stage.toUpperCase() + ' ' + code + ': ' + form.getPublishedUrl() + '   (edit: ' + form.getEditUrl() + ')');
    });
  });
  Logger.log(lines.join('\n'));
}

function buildForm(stage, code) {
  const isPre = stage === 'pre';
  const form = FormApp.create((isPre ? 'الاستبيان القبلي' : 'الاستبيان البعدي') + ' - النسخة ' + code);
  form.setDescription('دراسة لتقييم منصة تعليمية عن الارتباط الجيني. المشاركة تطوعية ولا تُجمع أي معلومات تعرّف بك، ويمكنك التوقف في أي وقت. نحن نقيّم المنصة لا نقيّمك، فأجب بما تعرفه دون الاستعانة بأي مصدر.');
  form.setConfirmationMessage('شكرًا لمشاركتك.');

  form.addTextItem().setTitle('رمز المشارك (مثل P01) — يعطيك إياه الباحث').setRequired(true);

  if (isPre) {
    form.addMultipleChoiceItem().setTitle('التخصص').setChoiceValues(DATA.profile.majors).setRequired(true);
    form.addMultipleChoiceItem().setTitle('السنة الدراسية').setChoiceValues(DATA.profile.years).setRequired(true);
    form.addMultipleChoiceItem().setTitle('هل سبق أن درست الارتباط الجيني (GWAS)؟').setChoiceValues(DATA.profile.prior_gwas).setRequired(true);
  }

  form.addPageBreakItem().setTitle('أسئلة المعرفة').setHelpText('اختر إجابة واحدة لكل سؤال.');
  DATA.forms[code].forEach((q, i) => {
    const item = form.addMultipleChoiceItem();
    item.setTitle('س' + (i + 1) + '. ' + q.text);
    if (q.card) {
      item.setHelpText(q.card + '\n\n' + q.question);
    }
    item.setChoiceValues(q.options);
    item.setRequired(true);
  });

  form.addPageBreakItem().setTitle('مدى ثقتك بنفسك').setHelpText('من 1 (غير واثق إطلاقًا) إلى 5 (واثق جدًا).');
  DATA.confidence.forEach(text => {
    form.addScaleItem().setTitle(text).setBounds(1, 5).setLabels('غير واثق إطلاقًا', 'واثق جدًا').setRequired(true);
  });

  if (!isPre) {
    form.addPageBreakItem().setTitle('رأيك في المنصة').setHelpText('من 1 (لا أوافق بشدة) إلى 5 (أوافق بشدة).');
    DATA.usefulness.forEach(text => {
      form.addScaleItem().setTitle(text).setBounds(1, 5).setLabels('لا أوافق بشدة', 'أوافق بشدة').setRequired(true);
    });
    DATA.open_questions.forEach(text => {
      form.addParagraphTextItem().setTitle(text).setRequired(false);
    });
  }
  return form;
}
"""


def apps_script(items: Optional[dict] = None) -> str:
    items = items or load_items()
    payload = {k: items[k] for k in ("forms", "confidence", "usefulness", "open_questions", "profile")}
    # The correct answers are not needed by the forms: leave them out of the script.
    for form in payload["forms"].values():
        for item in form:
            item.pop("correct", None)
            item.pop("verify", None)
    return APPS_SCRIPT.replace("__DATA__", json.dumps(payload, ensure_ascii=False, indent=2))


# --- command line ------------------------------------------------------------------

def write_template() -> None:
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=response_columns()).to_csv(STUDY_DIR / "responses_template.csv", index=False,
                                                   encoding="utf-8-sig")
    print("template ->", STUDY_DIR / "responses_template.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Learning study: pre/post knowledge test")
    parser.add_argument("action", nargs="?", default="analyse",
                        choices=["analyse", "template", "merge", "instrument", "script"])
    parser.add_argument("files", nargs="*", type=Path, help="merge: pre_A.csv pre_B.csv post_A.csv post_B.csv")
    args = parser.parse_args()

    if args.action == "template":
        write_template()
    elif args.action == "instrument":
        (STUDY_DIR / "instrument.md").write_text(instrument_markdown(), encoding="utf-8")
        print("written ->", STUDY_DIR / "instrument.md")
    elif args.action == "script":
        (STUDY_DIR / "google_forms.gs").write_text(apps_script(), encoding="utf-8")
        print("written ->", STUDY_DIR / "google_forms.gs")
    elif args.action == "merge":
        if len(args.files) != 4:
            raise SystemExit("merge needs four files: pre_A.csv pre_B.csv post_A.csv post_B.csv")
        frames = [pd.read_csv(f, encoding="utf-8-sig", dtype=str) for f in args.files]
        merged = merge_exports(*frames)
        merged[response_columns()].to_csv(RESPONSES, index=False, encoding="utf-8-sig")
        print(f"{len(merged)} participants with both tests -> {RESPONSES}")
    else:
        if not RESPONSES.exists():
            raise SystemExit(f"No responses yet: {RESPONSES}. Use 'merge' with the four Google Forms exports.")
        summary = analyse(pd.read_csv(RESPONSES, encoding="utf-8-sig", dtype=str))
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "learning_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                                       encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
