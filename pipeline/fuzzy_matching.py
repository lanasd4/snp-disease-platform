"""
Basic Fuzzy Matching Script
"""

from datetime import datetime
from difflib import SequenceMatcher
import json
import re
import sqlite3
import pandas as pd
from core.paths import DATABASE_PATH, get_project_root


def get_paths() -> dict:
    """Return important paths."""
    project_root = get_project_root()

    return {
        "project_root": project_root,
        "database": DATABASE_PATH,
        "outputs_tables": project_root / "outputs" / "tables",
    }


def ensure_directories() -> dict:
    """Create output folder if missing."""
    paths = get_paths()
    paths["outputs_tables"].mkdir(parents=True, exist_ok=True)
    return paths


def normalize_text(value) -> str:
    """Normalize Arabic and English text before comparison."""
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip().lower()

    # Remove Arabic diacritics
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    # Normalize common Arabic letters
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Keep Arabic letters, English letters, and numbers
    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    text = " ".join(text.split())

    return text


def token_overlap_score(query_norm: str, term_norm: str) -> float:
    """Calculate token overlap between query and term."""
    query_tokens = set(query_norm.split())
    term_tokens = set(term_norm.split())

    if not query_tokens or not term_tokens:
        return 0.0

    intersection = query_tokens.intersection(term_tokens)
    union = query_tokens.union(term_tokens)

    return len(intersection) / len(union)


def character_similarity_score(query_norm: str, term_norm: str) -> float:
    """Calculate character-level similarity using SequenceMatcher."""
    if not query_norm or not term_norm:
        return 0.0

    return SequenceMatcher(None, query_norm, term_norm).ratio()


def containment_score(query_norm: str, term_norm: str) -> float:
    """Give a strong score when one text contains the other."""
    if not query_norm or not term_norm:
        return 0.0

    if query_norm == term_norm:
        return 1.0

    if query_norm in term_norm or term_norm in query_norm:
        return 0.88

    return 0.0


def calculate_similarity(query_norm: str, term_norm: str) -> float:
    """Combine different similarity signals into one score."""
    char_score = character_similarity_score(query_norm, term_norm)
    token_score = token_overlap_score(query_norm, term_norm)
    contain_score = containment_score(query_norm, term_norm)

    final_score = max(
        char_score,
        token_score,
        contain_score
    )

    return round(float(final_score), 3)


def load_disease_terms() -> pd.DataFrame:
    """Load disease names and synonyms from SQLite."""
    paths = ensure_directories()
    database_path = paths["database"]

    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    with sqlite3.connect(database_path) as conn:
        disease_df = pd.read_sql_query(
            """
            SELECT
                disease_id,
                canonical_name,
                arabic_name
            FROM Disease
            """,
            conn
        )

        synonym_df = pd.read_sql_query(
            """
            SELECT
                ds.disease_id,
                ds.synonym,
                ds.language,
                ds.synonym_type,
                d.canonical_name,
                d.arabic_name
            FROM DiseaseSynonym ds
            JOIN Disease d ON ds.disease_id = d.disease_id
            """,
            conn
        )

    rows = []

    for _, row in disease_df.iterrows():
        rows.append({
            "disease_id": row["disease_id"],
            "canonical_name": row["canonical_name"],
            "arabic_name": row["arabic_name"],
            "term": row["canonical_name"],
            "term_source": "canonical_name"
        })

        if pd.notna(row["arabic_name"]):
            rows.append({
                "disease_id": row["disease_id"],
                "canonical_name": row["canonical_name"],
                "arabic_name": row["arabic_name"],
                "term": row["arabic_name"],
                "term_source": "arabic_name"
            })

    for _, row in synonym_df.iterrows():
        rows.append({
            "disease_id": row["disease_id"],
            "canonical_name": row["canonical_name"],
            "arabic_name": row["arabic_name"],
            "term": row["synonym"],
            "term_source": f"synonym:{row.get('language', '')}:{row.get('synonym_type', '')}"
        })

    terms_df = pd.DataFrame(rows)
    terms_df["normalized_term"] = terms_df["term"].apply(normalize_text)
    terms_df = terms_df[terms_df["normalized_term"] != ""].copy()
    terms_df = terms_df.drop_duplicates(subset=["disease_id", "normalized_term"])

    return terms_df


def suggest_closest_disease(query: str, limit: int = 5, min_score: float = 0.45) -> list:
    """Suggest closest diseases for a user query."""
    query_norm = normalize_text(query)

    if query_norm == "":
        return []

    terms_df = load_disease_terms()

    suggestion_rows = []

    for _, row in terms_df.iterrows():
        term_norm = row["normalized_term"]
        score = calculate_similarity(query_norm, term_norm)

        if score >= min_score:
            suggestion_rows.append({
                "query": query,
                "normalized_query": query_norm,
                "disease_id": row["disease_id"],
                "suggested_disease_name": row["canonical_name"],
                "suggested_disease_arabic_name": row["arabic_name"],
                "matched_term": row["term"],
                "term_source": row["term_source"],
                "score": score
            })

    if not suggestion_rows:
        return []

    suggestions_df = pd.DataFrame(suggestion_rows)

    # Keep the best suggestion per disease
    suggestions_df = (
        suggestions_df
        .sort_values(["score"], ascending=False)
        .drop_duplicates(subset=["disease_id"], keep="first")
        .sort_values(["score", "suggested_disease_name"], ascending=[False, True])
        .head(limit)
    )

    return suggestions_df.to_dict(orient="records")


def suggest_closest_disease_df(query: str, limit: int = 5, min_score: float = 0.45) -> pd.DataFrame:
    """Return suggestions as a DataFrame."""
    return pd.DataFrame(
        suggest_closest_disease(query=query, limit=limit, min_score=min_score)
    )


def run_fuzzy_tests() -> dict:
    paths = ensure_directories()

    test_queries = [
        "diabet",
        "diabetis",
        "type diabetes",
        "type ii diabetes",
        "t2 diab",
        "سكر",
        "السكر",
        "سكري",
        "السكري النوع الثاني",
        "hypertention",
        "blood presure",
        "الضغط",
        "ظغط",
        "astma",
        "ربو",
        "kidney diseas",
        "renal function",
        "obes",
        "bmi",
        "coronary heart",
        "cad"
    ]

    rows = []

    for query in test_queries:
        suggestions = suggest_closest_disease(query=query, limit=3, min_score=0.35)

        if suggestions:
            for rank, suggestion in enumerate(suggestions, start=1):
                rows.append({
                    "query": query,
                    "rank": rank,
                    "suggested_disease_name": suggestion.get("suggested_disease_name"),
                    "suggested_disease_arabic_name": suggestion.get("suggested_disease_arabic_name"),
                    "matched_term": suggestion.get("matched_term"),
                    "term_source": suggestion.get("term_source"),
                    "score": suggestion.get("score"),
                    "status": "suggestion_found"
                })
        else:
            rows.append({
                "query": query,
                "rank": None,
                "suggested_disease_name": None,
                "suggested_disease_arabic_name": None,
                "matched_term": None,
                "term_source": None,
                "score": None,
                "status": "no_suggestion"
            })

    tests_df = pd.DataFrame(rows)

    output_path = paths["outputs_tables"] / "fuzzy_matching_tests.csv"
    tests_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    summary = {
        "test_queries": len(test_queries),
        "rows_saved": len(tests_df),
        "queries_with_suggestions": int(
            tests_df[tests_df["status"] == "suggestion_found"]["query"].nunique()
        ),
        "output_path": str(output_path)
    }

    metadata_path = paths["outputs_tables"] / "fuzzy_matching_summary.json"

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "stage": "Basic Fuzzy Matching",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                **summary
            },
            file,
            ensure_ascii=False,
            indent=2
        )

    return summary


def main() -> None:
    result = run_fuzzy_tests()

    print("Fuzzy matching tests completed.")
    print(f"Test queries: {result['test_queries']}")
    print(f"Rows saved: {result['rows_saved']}")
    print(f"Queries with suggestions: {result['queries_with_suggestions']}")
    print(f"Output: {result['output_path']}")


if __name__ == "__main__":
    main()
