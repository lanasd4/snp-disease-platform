
"""
Tri Search Engine V1
"""

from functools import lru_cache
from pathlib import Path
import re
import pandas as pd

from core.diseases import resolve_disease
from core.paths import get_project_root


SEARCH_DATA_RELATIVE_PATH = Path("data") / "processed" / "ranked_associations_initial.csv"


def get_search_data_path() -> Path:
    return get_project_root() / SEARCH_DATA_RELATIVE_PATH


def safe_text(value, default="") -> str:
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip()

    if text == "" or text.lower() in {"nan", "none", "null"}:
        return default

    return text


def normalize_text(value) -> str:
    text = safe_text(value).lower()

    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)

    return " ".join(text.split())


def normalize_disease_query(query: str):
    """Map any known disease name or synonym (Arabic or English) to its canonical disease."""
    original = safe_text(query)
    disease = resolve_disease(original)
    if disease:
        return disease.name_en, True
    return original, False


def is_rsid_query(query: str) -> bool:
    return re.fullmatch(r"\s*rs\d+\s*", safe_text(query), flags=re.IGNORECASE) is not None


def load_tri_search_data() -> pd.DataFrame:
    """Ranked associations prepared for search; cached until the file changes."""
    path = get_search_data_path()

    if not path.exists():
        return pd.DataFrame()

    return _load_prepared(str(path), path.stat().st_mtime_ns).copy()


@lru_cache(maxsize=2)
def _load_prepared(path: str, mtime_ns: int) -> pd.DataFrame:
    return prepare_search_dataframe(pd.read_csv(path, dtype=str))


def prepare_search_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    required_columns = [
        "rsid",
        "gene_symbol",
        "disease_name",
        "disease_arabic_name",
        "importance_score",
        "rank_label",
        "rank_label_arabic",
        "p_value",
        "risk_allele",
        "source_database",
        "pubmed_id",
        "score_explanation_arabic",
    ]

    for col in required_columns:
        if col not in df.columns:
            df[col] = ""

    df["_rsid_norm"] = df["rsid"].apply(normalize_text)
    df["_gene_norm"] = df["gene_symbol"].apply(normalize_text)
    df["_disease_norm"] = df["disease_name"].apply(normalize_text)
    df["_disease_ar_norm"] = df["disease_arabic_name"].apply(normalize_text)

    df["importance_score_numeric"] = pd.to_numeric(
        df["importance_score"],
        errors="coerce"
    ).fillna(0)

    return df


def filter_arab_related(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    possible_cols = [
        "is_arab_related_rule",
        "is_arab_related_flag",
        "is_arab_related",
        "arab_related",
        "arab_tag",
    ]

    arab_cols = [c for c in possible_cols if c in df.columns]

    if not arab_cols:
        return pd.DataFrame(columns=df.columns)

    col = arab_cols[0]

    return df[
        df[col].astype(str).str.upper().isin(["Y", "YES", "TRUE", "1", "ARAB"])
    ].copy()


def _search_disease(df: pd.DataFrame, query: str):
    normalized_query, direct_known_query = normalize_disease_query(query)

    q_norm = normalize_text(normalized_query)
    raw_q_norm = normalize_text(query)

    # A query made only of punctuation/emoji/symbols normalizes to "".
    if not q_norm and not raw_q_norm:
        return df.iloc[0:0].copy(), normalized_query, direct_known_query

    exact = df[
        (df["_disease_norm"] == q_norm)
        | (df["_disease_ar_norm"] == raw_q_norm)
    ].copy()

    if not exact.empty:
        exact["matched_by"] = "disease_exact"
        return exact, normalized_query, direct_known_query

    partial = df[
        (q_norm != "" and df["_disease_norm"].str.contains(q_norm, na=False))
        | (raw_q_norm != "" and df["_disease_ar_norm"].str.contains(raw_q_norm, na=False))
    ].copy()

    partial["matched_by"] = "disease_partial"

    return partial, normalized_query, direct_known_query


def _search_snp(df: pd.DataFrame, query: str):
    q_norm = normalize_text(query)

    if not q_norm:
        return df.iloc[0:0].copy(), safe_text(query), is_rsid_query(query)

    exact = df[df["_rsid_norm"] == q_norm].copy()

    if not exact.empty:
        exact["matched_by"] = "snp_exact"
        return exact, safe_text(query), is_rsid_query(query)

    partial = df[df["_rsid_norm"].str.contains(q_norm, na=False)].copy()
    partial["matched_by"] = "snp_partial"

    return partial, safe_text(query), is_rsid_query(query)


def _search_gene(df: pd.DataFrame, query: str):
    q_norm = normalize_text(query)

    if not q_norm:
        return df.iloc[0:0].copy(), safe_text(query).upper(), False

    exact = df[df["_gene_norm"] == q_norm].copy()

    if not exact.empty:
        exact["matched_by"] = "gene_exact"
        return exact, safe_text(query).upper(), True

    partial = df[df["_gene_norm"].str.contains(q_norm, na=False)].copy()
    partial["matched_by"] = "gene_partial"

    return partial, safe_text(query).upper(), False


def search_tri_ranked_file(
    query: str,
    search_mode: str,
    arab_related_only: bool = False,
    limit: int = 20
) -> dict:
    df = load_tri_search_data()

    query = safe_text(query)
    search_mode = safe_text(search_mode).lower()

    if df.empty:
        return {
            "found": False,
            "query": query,
            "normalized_query": query,
            "direct_known_query": False,
            "search_mode": search_mode,
            "result_count": 0,
            "results": [],
            "message": "ranked_associations_initial.csv is missing or empty",
            "no_results_reason": "missing_data",
        }

    if search_mode == "disease":
        matched, normalized_query, direct_known_query = _search_disease(df, query)

    elif search_mode == "snp":
        matched, normalized_query, direct_known_query = _search_snp(df, query)

    elif search_mode == "gene":
        matched, normalized_query, direct_known_query = _search_gene(df, query)

    else:
        if is_rsid_query(query):
            matched, normalized_query, direct_known_query = _search_snp(df, query)
            search_mode = "snp"
        else:
            gene_matches, gene_norm, gene_known = _search_gene(df, query)

            if not gene_matches.empty:
                matched = gene_matches
                normalized_query = gene_norm
                direct_known_query = gene_known
                search_mode = "gene"
            else:
                matched, normalized_query, direct_known_query = _search_disease(df, query)
                search_mode = "disease"

    if arab_related_only:
        before_count = len(matched)
        matched = filter_arab_related(matched)

        if matched.empty and before_count > 0:
            return {
                "found": False,
                "query": query,
                "normalized_query": normalized_query,
                "direct_known_query": direct_known_query,
                "search_mode": search_mode,
                "result_count": 0,
                "results": [],
                "message": "No Arab-related records found for this valid query",
                "no_results_reason": "arab_filter_empty",
            }

    if not matched.empty:
        matched = matched.sort_values(
            "importance_score_numeric",
            ascending=False
        ).head(int(limit))

    helper_cols = [c for c in matched.columns if c.startswith("_")]
    matched = matched.drop(columns=helper_cols, errors="ignore")

    return {
        "found": not matched.empty,
        "query": query,
        "normalized_query": normalized_query,
        "direct_known_query": direct_known_query,
        "search_mode": search_mode,
        "result_count": int(len(matched)),
        "results": matched.to_dict(orient="records"),
        "message": "Tri search completed from ranked_associations_initial.csv",
        "no_results_reason": "none" if not matched.empty else "no_direct_match",
    }


def summarize_search_data() -> dict:
    df = load_tri_search_data()

    if df.empty:
        return {
            "rows": 0,
            "diseases": 0,
            "genes": 0,
            "snps": 0,
        }

    return {
        "rows": int(len(df)),
        "diseases": int(df["disease_name"].nunique()) if "disease_name" in df.columns else 0,
        "genes": int(df["gene_symbol"].nunique()) if "gene_symbol" in df.columns else 0,
        "snps": int(df["rsid"].nunique()) if "rsid" in df.columns else 0,
    }
