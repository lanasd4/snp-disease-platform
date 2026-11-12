
"""
Glossary Engine
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import re
from core.paths import get_project_root


DEFAULT_GLOSSARY_COLUMNS = [
    "term",
    "arabic_term",
    "category",
    "english_definition",
    "arabic_definition",
    "simple_explanation",
    "example",
    "safe_note",
    "created_at",
    "updated_at",
    "is_active",
]


def get_glossary_path() -> Path:
    return get_project_root() / "data" / "metadata" / "glossary_terms.csv"


def load_glossary(active_only: bool = True) -> pd.DataFrame:
    path = get_glossary_path()

    if not path.exists():
        return pd.DataFrame(columns=DEFAULT_GLOSSARY_COLUMNS)

    df = pd.read_csv(path)

    for col in DEFAULT_GLOSSARY_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if active_only and "is_active" in df.columns:
        df = df[df["is_active"].astype(str).isin(["1", "True", "true", "YES", "yes"])].copy()

    return df.reset_index(drop=True)


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""

    return str(value).strip().lower()


def search_glossary(query: str, limit: int = 20) -> pd.DataFrame:
    df = load_glossary(active_only=True)

    if df.empty:
        return df

    q = normalize_text(query)

    if not q:
        return df.head(limit)

    search_cols = [
        "term",
        "arabic_term",
        "category",
        "english_definition",
        "arabic_definition",
        "simple_explanation",
    ]

    mask = pd.Series(False, index=df.index)

    for col in search_cols:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(re.escape(q), na=False)

    return df[mask].head(limit).reset_index(drop=True)


def get_term_definition(term: str) -> Optional[Dict[str, Any]]:
    df = load_glossary(active_only=True)

    if df.empty:
        return None

    q = normalize_text(term)

    exact = df[
        df["term"].astype(str).str.lower().eq(q)
        | df["arabic_term"].astype(str).str.lower().eq(q)
    ]

    if not exact.empty:
        return exact.iloc[0].to_dict()

    contains = search_glossary(term, limit=1)

    if not contains.empty:
        return contains.iloc[0].to_dict()

    return None


def detect_relevant_terms_from_columns(columns: List[str]) -> List[str]:
    joined = " ".join([str(c).lower() for c in columns])

    rules = {
        "SNP": ["snp", "rsid", "variant"],
        "rsID": ["rsid", "rs_id"],
        "Gene": ["gene", "gene_symbol", "mapped_gene"],
        "Disease / Trait": ["disease", "trait", "phenotype"],
        "p-value": ["p_value", "p-value", "pvalue"],
        "Odds Ratio": ["odds_ratio", "or"],
        "Beta / Effect size": ["effect_size", "beta"],
        "Risk allele": ["risk_allele", "effect_allele"],
        "Population": ["population", "ancestry", "region", "country"],
        "Study title": ["study_title", "study"],
        "PubMed ID": ["pubmed", "pmid"],
        "Importance score": ["importance_score"],
        "Rank label": ["rank_label"],
        "Arab-related evidence": ["arab", "middle", "regional"],
    }

    detected = []

    for term, keywords in rules.items():
        if any(keyword in joined for keyword in keywords):
            detected.append(term)

    return detected


def detect_relevant_terms_from_result(row: Dict[str, Any]) -> List[str]:
    if row is None:
        return []

    if not isinstance(row, dict):
        try:
            row = dict(row)
        except Exception:
            return []

    detected = detect_relevant_terms_from_columns(list(row.keys()))

    core_terms = ["SNP", "rsID", "Gene", "Disease / Trait", "Association", "p-value"]

    for term in core_terms:
        if term not in detected:
            detected.append(term)

    return detected


def get_relevant_glossary_for_result(row: Dict[str, Any]) -> pd.DataFrame:
    df = load_glossary(active_only=True)

    if df.empty:
        return df

    terms = detect_relevant_terms_from_result(row)

    if not terms:
        return df.head(10)

    mask = df["term"].astype(str).isin(terms)

    result = df[mask].copy()

    order_map = {term: i for i, term in enumerate(terms)}
    result["order"] = result["term"].map(order_map).fillna(999)
    result = result.sort_values("order").drop(columns=["order"])

    return result.reset_index(drop=True)


def build_glossary_context_for_ai(row: Dict[str, Any], max_terms: int = 10) -> str:
    relevant_df = get_relevant_glossary_for_result(row).head(max_terms)

    if relevant_df.empty:
        return ""

    lines = []

    for _, item in relevant_df.iterrows():
        term = str(item.get("term", "")).strip()
        arabic_term = str(item.get("arabic_term", "")).strip()
        arabic_definition = str(item.get("arabic_definition", "")).strip()
        safe_note = str(item.get("safe_note", "")).strip()

        line = f"- {term} ({arabic_term}): {arabic_definition}"

        if safe_note:
            line += f" ملاحظة: {safe_note}"

        lines.append(line)

    return "\n".join(lines)


def export_glossary_summary() -> Path:
    df = load_glossary(active_only=True)

    outputs_dir = get_project_root() / "outputs" / "tables"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    summary_path = outputs_dir / "glossary_summary.csv"

    if df.empty:
        pd.DataFrame(columns=["category", "term_count"]).to_csv(
            summary_path,
            index=False,
            encoding="utf-8-sig"
        )
        return summary_path

    summary_df = df.groupby("category", dropna=False).size().reset_index(name="term_count")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    return summary_path
