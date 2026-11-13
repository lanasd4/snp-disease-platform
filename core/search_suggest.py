"""
Search helpers: autocomplete options and "did you mean ...?" suggestions.

Suggestions use string similarity on normalized text (Arabic letter forms and
the definite article are unified first), so typos such as "سكنة" -> "السمنة"
or "Diabetis" -> "Diabetes" still find the intended disease, gene or variant.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
from typing import Optional

import pandas as pd

from core.diseases import list_diseases, normalize_term, resolve_disease

DISEASE_CUTOFF = 0.6
GENE_CUTOFF = 0.75
SNP_CUTOFF = 0.85


def _strip_article(text: str) -> str:
    return text[2:] if text.startswith("ال") and len(text) > 3 else text


@lru_cache(maxsize=1)
def _disease_aliases() -> dict:
    """Normalized alias (also without the Arabic article) -> canonical English name."""
    aliases = {}
    for disease in list_diseases():
        for name in (*disease.synonyms, *disease.gwas_traits):
            key = normalize_term(name)
            if key:
                aliases.setdefault(key, disease.name_en)
                aliases.setdefault(_strip_article(key), disease.name_en)
    return aliases


def suggest_disease(query: str) -> Optional[str]:
    """Closest disease (English canonical name) for a misspelled query, else None."""
    key = _strip_article(normalize_term(query))
    if not key or resolve_disease(query):
        return None
    aliases = _disease_aliases()
    match = get_close_matches(key, list(aliases), n=1, cutoff=DISEASE_CUTOFF)
    if match:
        return aliases[match[0]]
    # A longer phrase containing a disease name, e.g. "مرض السمنه عند الاطفال".
    for alias, name in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 3 and re.search(rf"(^| ){re.escape(alias)}( |$)", key):
            return name
    return None


def _closest(query: str, candidates: list, cutoff: float) -> Optional[str]:
    if not query or not candidates:
        return None
    upper = {str(c).upper(): c for c in candidates}
    match = get_close_matches(query.strip().upper(), list(upper), n=1, cutoff=cutoff)
    return upper[match[0]] if match else None


def gene_symbols(data: pd.DataFrame) -> list:
    """Individual gene symbols in the data (fields like "A - B" are split)."""
    if data.empty or "gene_symbol" not in data.columns:
        return []
    genes = set()
    for field in data["gene_symbol"].dropna().astype(str):
        for part in re.split(r"\s+-\s+|[,;/]", field):
            part = part.strip()
            if part and part.lower() not in {"nan", "none", "na"}:
                genes.add(part.upper())
    return sorted(genes)


def rsids(data: pd.DataFrame) -> list:
    if data.empty or "rsid" not in data.columns:
        return []
    return sorted(set(data["rsid"].dropna().astype(str).str.lower()), key=lambda r: (len(r), r))


def suggest(query: str, mode: str, data: pd.DataFrame) -> Optional[tuple]:
    """Return (mode, value) to search instead, or None. May switch mode, e.g. a gene typed as a disease."""
    text = (query or "").strip()
    if not text:
        return None
    if re.fullmatch(r"rs\d+", text, flags=re.IGNORECASE) and mode != "snp":
        return ("snp", text.lower())
    genes = gene_symbols(data)
    if mode != "gene" and text.upper() in set(genes):
        return ("gene", text.upper())
    if mode != "disease" and resolve_disease(text):
        return ("disease", text)

    if mode == "disease":
        name = suggest_disease(text)
        return ("disease", name) if name else None
    if mode == "gene":
        gene = _closest(text, genes, GENE_CUTOFF)
        return ("gene", gene) if gene and gene.upper() != text.upper() else None
    if mode == "snp":
        rsid = _closest(text, rsids(data), SNP_CUTOFF)
        return ("snp", rsid.lower()) if rsid and rsid.lower() != text.lower() else None
    return None


def autocomplete_options(mode: str, data: pd.DataFrame, arabic: bool) -> list:
    """Options for the search box, in the interface language first."""
    if mode == "disease":
        first, second, extra = [], [], []
        for disease in list_diseases():
            first.append(disease.name_ar if arabic else disease.name_en)
            second.append(disease.name_en if arabic else disease.name_ar)
            extra.extend(disease.synonyms)
        return list(dict.fromkeys(first + second + extra))
    if mode == "gene":
        return gene_symbols(data)
    return rsids(data)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_term(a), normalize_term(b)).ratio()
