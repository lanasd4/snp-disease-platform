"""
Turn processed admin sources into rows of the active ranked file and re-rank.

New rows get the same evidence levels as the rest of the data (core.evidence),
so a merged source is indistinguishable from the original dataset. Every added row keeps its source id, which lets a
merge be rolled back on its own without touching other sources.
"""

from __future__ import annotations

import math
from typing import Tuple

import pandas as pd

from core.diseases import resolve_disease_or_trait as resolve_disease
from core.regions import ancestry_label, is_arab
from core.evidence import assign_evidence

SOURCE_COLUMN = "admin_upload_source_id"


def _text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _number(value):
    try:
        number = float(_text(value))
    except ValueError:
        return None
    return None if math.isnan(number) else number


def _neg_log10(p):
    return round(-math.log10(p), 4) if p and p > 0 else None


def _allele(value) -> str:
    """GWAS gives 'rs7903146-T'; keep the allele, drop '?' placeholders."""
    text = _text(value).split("-")[-1].strip().upper()
    return text if text and text != "?" and not text.startswith("RS") else ""


def _pubmed(value) -> str:
    text = _text(value)
    number = _number(text)
    return str(int(number)) if number is not None and number.is_integer() else text


def build_source_rows(processed_df: pd.DataFrame, source_id: str, active_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (rows ready to add, rows skipped with a reason)."""
    snp_ids = dict(zip(active_df["rsid"].astype(str).str.lower(), active_df["snp_id"].astype(str)))
    gene_ids = dict(zip(active_df["gene_symbol"].astype(str).str.upper(), active_df["gene_id"].astype(str)))

    rows, skipped = [], []
    for index, record in processed_df.iterrows():
        disease = resolve_disease(_text(record.get("disease_name")))
        p_value = _number(record.get("p_value"))
        rsid = _text(record.get("rsid")).lower()
        reason = ""
        if disease is None:
            reason = "disease_not_on_platform"
        elif p_value is None or not 0 < p_value <= 1:
            reason = "p_value_out_of_range"
        if reason:
            skipped.append({**record.to_dict(), "skip_reason": reason})
            continue

        gene = _text(record.get("gene_symbol")).upper()
        population_text = " ".join(filter(None, (_text(record.get("population")), _text(record.get("country")))))
        odds_ratio, effect = _number(record.get("odds_ratio")), _number(record.get("effect_size"))
        risk_allele = _allele(record.get("risk_allele")) or _allele(record.get("effect_allele"))
        pubmed = _pubmed(record.get("pubmed_id"))
        study_title = _text(record.get("study_title"))
        arab = is_arab(population_text)
        rows.append({
            "association_db_rowid": f"{source_id}:{index}",
            "disease_id": disease.disease_id,
            "disease_name": disease.name_en,
            "disease_arabic_name": disease.name_ar,
            "snp_id": snp_ids.get(rsid, f"ADM_{rsid}"),
            "rsid": rsid,
            "gene_id": gene_ids.get(gene, ""),
            "gene_symbol": gene,
            "p_value": p_value,
            "p_value_numeric": p_value,
            "p_value_strength": _neg_log10(p_value),
            "p_value_strength_capped": min(_neg_log10(p_value) or 0, 300.0),
            "odds_ratio": odds_ratio if odds_ratio is not None else "",
            "odds_ratio_numeric": odds_ratio,
            "effect_size": effect if effect is not None else "",
            "effect_size_numeric": effect,
            "has_or_beta": int(odds_ratio is not None or effect is not None),
            "risk_allele": risk_allele,
            "has_risk_allele": int(bool(risk_allele)),
            "study_title": study_title,
            "pubmed_id": pubmed,
            "publication_year": _text(record.get("publication_year")),
            "journal": "",
            "has_pubmed_id": int(bool(pubmed)),
            "has_study_title": int(bool(study_title)),
            "population_label": ancestry_label(population_text) if population_text else "",
            "region": _text(record.get("region")),
            "ancestry": population_text,
            "is_arab_related": "Yes" if arab else "No",
            "is_arab_related_flag": int(arab),
            "has_population_context": int(bool(population_text or _text(record.get("region")))),
            "source_database_clean": _text(record.get("source_database")) or "admin_upload",
            "evidence_level": "admin_upload",
            SOURCE_COLUMN: source_id,
        })
    return pd.DataFrame(rows), pd.DataFrame(skipped)


def rerank(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute evidence levels and order for the whole table."""
    df = df.copy()
    if SOURCE_COLUMN not in df.columns:
        df[SOURCE_COLUMN] = ""
    df[SOURCE_COLUMN] = df[SOURCE_COLUMN].fillna("")
    return assign_evidence(df)


def add_source(active_df: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([active_df, new_rows], ignore_index=True, sort=False)
    return rerank(combined)[_column_order(active_df, combined)]


def remove_source(active_df: pd.DataFrame, source_id: str) -> pd.DataFrame:
    if SOURCE_COLUMN not in active_df.columns:
        return active_df.copy()
    kept = active_df[active_df[SOURCE_COLUMN].fillna("").astype(str) != str(source_id)]
    return rerank(kept)[_column_order(active_df, kept)]


def _column_order(active_df: pd.DataFrame, combined: pd.DataFrame) -> list:
    columns = list(active_df.columns)
    if SOURCE_COLUMN not in columns:
        columns.append(SOURCE_COLUMN)
    return columns
