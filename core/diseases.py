"""
Disease registry: the single source of truth for the diseases the platform covers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import pandas as pd

from core.paths import DISEASE_PROFILES_FILE, DISEASE_SYNONYMS_FILE, MASTER_DISEASES_FILE

_ARABIC_DIACRITICS = re.compile(r"[ً-ٰٟ]")
_ARABIC_LETTER_FORMS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه"})


@dataclass(frozen=True)
class Disease:
    disease_id: int
    name_en: str
    name_ar: str
    category: str
    icon: str = "🧬"
    description_ar: str = ""
    description_en: str = ""
    gwas_traits: Tuple[str, ...] = ()
    synonyms: Tuple[str, ...] = field(default=())

    def display_name(self, arabic: bool) -> str:
        return self.name_ar if arabic else self.name_en

    def description(self, arabic: bool) -> str:
        return self.description_ar if arabic else self.description_en


def normalize_term(text: str) -> str:
    """Lower-case, unify Arabic letter forms, drop diacritics and punctuation."""
    text = _ARABIC_DIACRITICS.sub("", str(text or "").strip().lower())
    text = text.translate(_ARABIC_LETTER_FORMS)
    text = re.sub(r"[^a-z0-9؀-ۿ]+", " ", text)
    return " ".join(text.split())


def _read_csv(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("") if path.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def list_diseases() -> Tuple[Disease, ...]:
    """Active diseases ordered by id."""
    master = _read_csv(MASTER_DISEASES_FILE)
    synonyms = _read_csv(DISEASE_SYNONYMS_FILE)
    profiles = _read_csv(DISEASE_PROFILES_FILE)
    profile_by_id = {row["disease_id"]: row for _, row in profiles.iterrows()} if not profiles.empty else {}

    diseases: List[Disease] = []
    for _, row in master.iterrows():
        if row.get("active", "Y").strip().upper() != "Y":
            continue
        disease_id = row["disease_id"]
        profile = profile_by_id.get(disease_id, {})
        names = synonyms[synonyms["disease_id"] == disease_id]["synonym"].tolist() if not synonyms.empty else []
        diseases.append(Disease(
            disease_id=int(disease_id),
            name_en=row["canonical_name"],
            name_ar=row["arabic_name"],
            category=row.get("category", ""),
            icon=profile.get("icon", "") or "🧬",
            description_ar=profile.get("description_ar", ""),
            description_en=profile.get("description_en", ""),
            gwas_traits=tuple(t.strip().lower() for t in profile.get("gwas_mapped_traits", "").split(";") if t.strip()),
            synonyms=tuple(dict.fromkeys([row["canonical_name"], row["arabic_name"], *names])),
        ))
    return tuple(sorted(diseases, key=lambda d: d.disease_id))


@lru_cache(maxsize=1)
def _alias_index() -> Dict[str, Disease]:
    index: Dict[str, Disease] = {}
    for disease in list_diseases():
        for alias in disease.synonyms:
            key = normalize_term(alias)
            if key:
                index.setdefault(key, disease)
                # Arabic definite article: "السمنة" and "سمنة" mean the same thing.
                if key.startswith("ال") and len(key) > 3:
                    index.setdefault(key[2:], disease)
    return index


def resolve_disease(query: str) -> Optional[Disease]:
    """Return the disease a free-text query names (any synonym, Arabic or English), else None."""
    key = normalize_term(query)
    if not key:
        return None
    index = _alias_index()
    return index.get(key) or (index.get(key[2:]) if key.startswith("ال") else None)


def resolve_disease_or_trait(text: str) -> Optional[Disease]:
    """Like resolve_disease, but also accepts the GWAS Catalog trait names of each disease."""
    disease = resolve_disease(text)
    if disease is not None:
        return disease
    key = normalize_term(text)
    for candidate in list_diseases():
        if key and key in {normalize_term(trait) for trait in candidate.gwas_traits}:
            return candidate
    return None


def get_disease(name_or_id) -> Optional[Disease]:
    for disease in list_diseases():
        if str(name_or_id) in (str(disease.disease_id), disease.name_en):
            return disease
    return resolve_disease(str(name_or_id))


def clear_cache() -> None:
    """Forget cached registry data (after the data files change)."""
    list_diseases.cache_clear()
    _alias_index.cache_clear()
