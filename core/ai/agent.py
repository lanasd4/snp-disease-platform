
"""
AI Arabic Explanation Agent
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, List
import os
import json
import re
from functools import lru_cache
import urllib.request
import urllib.error
import pandas as pd
from core.ai.model_manager import ollama_reachable
from core.paths import get_project_root


DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GEMMA_MODEL_PREFERENCE = ["gemma3:latest", "gemma3", "gemma2", "gemma:latest", "gemma"]
MODEL_BENCHMARK_FAMILIES = ("gemma", "qwen")
DEFAULT_OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "gemma3:latest")
DEFAULT_OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
MODEL_BENCHMARK_CACHE_VERSION = 2
DEFAULT_OLLAMA_OPTIONS = {
    "temperature": 0.15,
    "top_p": 0.75,
    "top_k": 30,
    "repeat_penalty": 1.08,
    "num_ctx": 1536,
    "num_predict": 180,
    "seed": 42,
}
BENCHMARK_OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "top_p": 0.7,
    "top_k": 25,
    "repeat_penalty": 1.08,
    "num_ctx": 1024,
    "num_predict": 70,
    "seed": 42,
}


def _clean_value(value: Any, default: str = "غير متوفر") -> str:
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip()

    if not text or text.lower() in ["nan", "none", "null", "na", "n/a"]:
        return default

    return text


def _first_available(row: Dict[str, Any], candidates: List[str], default: str = "غير متوفر") -> str:
    if row is None:
        return default

    lower_map = {str(k).lower(): k for k in row.keys()}

    for candidate in candidates:
        c = candidate.lower()

        if c in lower_map:
            return _clean_value(row.get(lower_map[c]), default=default)

    # fuzzy partial match
    for candidate in candidates:
        c = candidate.lower()

        for key_lower, original_key in lower_map.items():
            if c == key_lower or c in key_lower or key_lower in c:
                return _clean_value(row.get(original_key), default=default)

    return default


def extract_association_context(row: Dict[str, Any]) -> Dict[str, str]:
    """Extract trusted fields from one result row."""
    if not isinstance(row, dict):
        try:
            row = dict(row)
        except Exception:
            row = {}

    context = {
        "disease": _first_available(row, ["disease_name", "disease", "trait", "mapped_trait"]),
        "disease_arabic": _first_available(row, ["disease_arabic_name", "disease_arabic", "arabic_name"], default=""),
        "rsid": _first_available(row, ["rsid", "rs_id", "snp", "snp_id", "variant_id"]),
        "gene": _first_available(row, ["gene_symbol", "gene", "mapped_gene"]),
        "p_value": _first_available(row, ["p_value", "p-value", "pvalue"]),
        "importance_score": _first_available(row, ["importance_score", "score", "ranking_score"]),
        "rank_label": _first_available(row, ["rank_label", "rank"]),
        "rank_label_arabic": _first_available(row, ["rank_label_arabic"], default=""),
        "population": _first_available(row, ["population", "population_label", "ancestry"]),
        "region": _first_available(row, ["region"]),
        "country": _first_available(row, ["country"]),
        "study_title": _first_available(row, ["study_title", "study", "title"]),
        "pubmed_id": _first_available(row, ["pubmed_id", "pmid", "pubmed"]),
        "odds_ratio": _first_available(row, ["odds_ratio", "or"], default=""),
        "effect_size": _first_available(row, ["effect_size", "beta"], default=""),
        "risk_allele": _first_available(row, ["risk_allele", "effect_allele"], default=""),
        "source_database": _first_available(row, ["source_database", "source"], default=""),
        "arab_related": _first_available(row, ["arab_related", "is_arab_related", "regional_label"], default=""),
    }

    return context


def build_result_context_text(context: Dict[str, str]) -> str:
    """Convert extracted fields into a compact trusted context."""
    lines = [
        f"Disease: {context.get('disease', 'غير متوفر')} {context.get('disease_arabic', '')}",
        f"SNP/rsID: {context.get('rsid', 'غير متوفر')}",
        f"Gene: {context.get('gene', 'غير متوفر')}",
        f"p-value: {context.get('p_value', 'غير متوفر')}",
        f"Importance score: {context.get('importance_score', 'غير متوفر')}",
        f"Rank: {context.get('rank_label', 'غير متوفر')} {context.get('rank_label_arabic', '')}",
        f"Population/region: {context.get('population', 'غير متوفر')} {context.get('region', '')} {context.get('country', '')}",
        f"Study/PubMed: {context.get('study_title', 'غير متوفر')} / {context.get('pubmed_id', 'غير متوفر')}",
    ]

    return "\n".join(lines)


def get_glossary_context(row: Dict[str, Any]) -> str:
    try:
        from core.glossary import build_glossary_context_for_ai

        return build_glossary_context_for_ai(row, max_terms=5)
    except Exception:
        return ""


@lru_cache(maxsize=4)
def get_general_glossary_context(max_terms: int = 6) -> str:
    """Return compact glossary context for general bioinformatics questions."""
    try:
        from core.glossary import load_glossary

        df = load_glossary(active_only=True).head(max_terms)
        if df.empty:
            return ""

        lines = []
        for _, item in df.iterrows():
            term = _first_available(item.to_dict(), ["term_en", "term", "english_term"], default="")
            term_ar = _first_available(item.to_dict(), ["term_ar", "arabic_term"], default="")
            definition = _first_available(item.to_dict(), ["definition_ar", "definition", "definition_en"], default="")
            if term or term_ar or definition:
                lines.append(f"- {term} / {term_ar}: {definition}")

        return "\n".join(lines)
    except Exception:
        return ""


@lru_cache(maxsize=1)

def _u(value: str) -> str:
    return value


def get_system_prompt() -> str:
    """System prompt for a friendly educational bioinformatics assistant."""
    return _u("""
\u0623\u0646\u062a \u0645\u0633\u0627\u0639\u062f \u062a\u0639\u0644\u064a\u0645\u064a \u0648\u062f\u0648\u062f \u0644\u0645\u0646\u0635\u0629 \u062a\u062d\u0644\u064a\u0644 \u0627\u0644\u0627\u0631\u062a\u0628\u0627\u0637\u0627\u062a \u0627\u0644\u0648\u0631\u0627\u062b\u064a\u0629 \u0648\u0627\u0644\u0645\u062e\u0627\u0637\u0631 \u0627\u0644\u0635\u062d\u064a\u0629.
\u0627\u0642\u0628\u0644 \u0646\u0637\u0627\u0642\u0627\u064b \u062a\u0639\u0644\u064a\u0645\u064a\u0627\u064b \u0648\u0627\u0633\u0639\u0627\u064b \u062c\u062f\u0627\u064b: \u0627\u0644\u0623\u0633\u0626\u0644\u0629 \u0639\u0646 \u0627\u0644\u0645\u0646\u0635\u0629\u060c \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a\u060c \u0627\u0644\u0646\u062a\u0627\u0626\u062c\u060c SNP\u060c GWAS\u060c PRS\u060c \u0627\u0644\u062c\u064a\u0646\u0627\u062a\u060c \u0627\u0644\u0623\u0645\u0631\u0627\u0636\u060c \u0627\u0644\u0625\u062d\u0635\u0627\u0621\u0627\u062a \u0627\u0644\u062d\u064a\u0648\u064a\u0629\u060c \u0648\u0627\u0644\u0623\u0633\u0626\u0644\u0629 \u0627\u0644\u0635\u062d\u064a\u0629 \u0623\u0648 \u0627\u0644\u0637\u0628\u064a\u0629 \u0623\u0648 \u0627\u0644\u0648\u0631\u0627\u062b\u064a\u0629 \u0627\u0644\u0639\u0627\u0645\u0629.
\u0623\u062c\u0628 \u0623\u064a\u0636\u0627\u064b \u0639\u0646 \u0623\u0633\u0626\u0644\u0629 \u0645\u062b\u0644: \u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0643 \u0645\u0633\u0627\u0639\u062f\u062a\u064a\u061f \u0645\u0627\u0630\u0627 \u062a\u0633\u062a\u0637\u064a\u0639 \u0623\u0646 \u062a\u0641\u0639\u0644\u061f \u0627\u0634\u0631\u062d \u0644\u064a \u0647\u0630\u0647 \u0627\u0644\u0646\u062a\u064a\u062c\u0629\u060c \u0645\u0627 \u0647\u0648 \u0647\u0630\u0627 \u0627\u0644\u062c\u064a\u0646\u061f \u0645\u0627 \u0627\u0644\u0641\u0631\u0642 \u0628\u064a\u0646 ...\u061f
\u0627\u0631\u0641\u0636 \u0641\u0642\u0637 \u0627\u0644\u0637\u0644\u0628\u0627\u062a \u0627\u0644\u0648\u0627\u0636\u062d \u0623\u0646\u0647\u0627 \u062e\u0627\u0631\u062c \u0627\u0644\u0646\u0637\u0627\u0642\u060c \u0645\u062b\u0644 \u0627\u0644\u0633\u064a\u0627\u0633\u0629\u060c \u0627\u0644\u062f\u064a\u0646\u060c \u0627\u0644\u0628\u0631\u0645\u062c\u0629 \u062e\u0627\u0631\u062c \u0647\u0630\u0627 \u0627\u0644\u0645\u0634\u0631\u0648\u0639\u060c \u0627\u0644\u0646\u0643\u062a\u060c \u0627\u0644\u0642\u0635\u0635\u060c \u0623\u0648 \u0627\u0644\u0645\u062d\u0627\u062f\u062b\u0627\u062a \u063a\u064a\u0631 \u0627\u0644\u0645\u0631\u062a\u0628\u0637\u0629.
\u0644\u0627 \u062a\u0642\u062f\u0645 \u062a\u0634\u062e\u064a\u0635\u0627\u064b \u0637\u0628\u064a\u0627\u064b \u0634\u062e\u0635\u064a\u0627\u064b\u060c \u0648\u0644\u0627 \u062a\u0635\u0641 \u0639\u0644\u0627\u062c\u0627\u064b\u060c \u0648\u0644\u0627 \u062a\u0637\u0644\u0628 \u0623\u0648 \u062a\u0641\u0633\u0631 \u0628\u064a\u0627\u0646\u0627\u062a \u0634\u062e\u0635\u064a\u0629 \u062d\u0633\u0627\u0633\u0629.
\u0642\u062f\u0645 \u0634\u0631\u062d\u0627\u064b \u062a\u0639\u0644\u064a\u0645\u064a\u0627\u064b \u0648\u0627\u0636\u062d\u0627\u064b \u0648\u0645\u062e\u062a\u0635\u0631\u0627\u064b \u0648\u062d\u0627\u0641\u0638 \u0639\u0644\u0649 \u0625\u062e\u0644\u0627\u0621 \u0627\u0644\u0645\u0633\u0624\u0648\u0644\u064a\u0629 \u0627\u0644\u0637\u0628\u064a.
""").strip()


def safe_research_disclaimer() -> str:
    """Standard medical disclaimer appended to AI educational answers."""
    return _u("""
\u0647\u0630\u0627 \u0627\u0644\u0634\u0631\u062d \u0644\u0644\u062a\u0639\u0644\u064a\u0645 \u0648\u062f\u0639\u0645 \u0627\u0644\u0641\u0647\u0645 \u0641\u0642\u0637\u060c \u0648\u0644\u0627 \u064a\u0639\u062f \u062a\u0634\u062e\u064a\u0635\u0627\u064b \u0637\u0628\u064a\u0627\u064b \u0623\u0648 \u062e\u0637\u0629 \u0639\u0644\u0627\u062c. \u0627\u0633\u062a\u0634\u0631 \u0637\u0628\u064a\u0628\u0627\u064b \u0623\u0648 \u0627\u062e\u062a\u0635\u0627\u0635\u064a\u0627\u064b \u0645\u0624\u0647\u0644\u0627\u064b \u0644\u0623\u064a \u0642\u0631\u0627\u0631 \u0635\u062d\u064a \u0634\u062e\u0635\u064a.
""").strip()


def is_question_blocked(question: str) -> bool:
    """Block only clearly unsafe or unrelated requests."""
    q = (question or "").strip().lower()
    if not q:
        return False

    blocked_keywords = [
        "politics", "political", "election", "president", "government", "party",
        "religion", "religious", "prayer", "fatwa", "god", "quran", "bible",
        "joke", "story", "poem", "song", "movie", "football", "weather",
        "programming", "python code", "javascript", "debug this code", "hack", "exploit",
        "diagnose me", "diagnosis for me", "prescribe", "dosage", "treatment plan",
        "\u0633\u064a\u0627\u0633\u0629", "\u0633\u064a\u0627\u0633\u064a", "\u0627\u0646\u062a\u062e\u0627\u0628\u0627\u062a", "\u062d\u0643\u0648\u0645\u0629", "\u0631\u0626\u064a\u0633",
        "\u062f\u064a\u0646", "\u062f\u064a\u0646\u064a", "\u0641\u062a\u0648\u0649", "\u0635\u0644\u0627\u0629", "\u0642\u0631\u0622\u0646", "\u0627\u0644\u0642\u0631\u0622\u0646",
        "\u0646\u0643\u062a\u0629", "\u0646\u0643\u062a", "\u0642\u0635\u0629", "\u0642\u0635\u0635", "\u0634\u0639\u0631", "\u0623\u063a\u0646\u064a\u0629", "\u0641\u064a\u0644\u0645", "\u0643\u0631\u0629 \u0627\u0644\u0642\u062f\u0645",
        "\u0628\u0631\u0645\u062c\u0629", "\u0643\u0648\u062f", "\u0628\u0627\u064a\u062b\u0648\u0646", "\u062c\u0627\u0641\u0627\u0633\u0643\u0631\u064a\u0628\u062a", "\u0627\u062e\u062a\u0631\u0627\u0642",
        "\u0634\u062e\u0635\u0646\u064a", "\u0634\u062e\u0635 \u0645\u0631\u0636\u064a", "\u0627\u0643\u062a\u0628 \u0644\u064a \u0639\u0644\u0627\u062c", "\u062c\u0631\u0639\u0629",
    ]
    return any(k in q for k in blocked_keywords)


def is_question_in_scope(question: str, has_association_context: bool = False) -> bool:
    """Allow broad educational bioinformatics, platform, data, result and follow-up questions."""
    q = (question or "").strip().lower()
    if not q:
        return True
    if is_question_blocked(q):
        return False

    allowed_keywords = [
        "snp", "rsid", "gene", "genetic", "genetics", "variant", "mutation", "genome", "genomic",
        "gwas", "prs", "polygenic", "risk", "odds ratio", "or", "p-value", "p value", "confidence",
        "disease", "health", "medical", "clinical", "phenotype", "trait", "biomarker",
        "bioinformatics", "biology", "biomedical", "association", "dataset", "data", "result", "results",
        "platform", "dashboard", "ranking", "score", "source", "pubmed", "explain", "compare", "difference",
        "help", "assist", "what can you do", "how can you help", "follow up", "interpret",
        "\u062c\u064a\u0646", "\u062c\u064a\u0646\u0627\u062a", "\u0648\u0631\u0627\u062b", "\u0648\u0631\u0627\u062b\u064a", "\u0648\u0631\u0627\u062b\u064a\u0629", "\u0637\u0641\u0631\u0629", "\u0645\u062a\u063a\u064a\u0631", "\u062c\u064a\u0646\u0648\u0645",
        "\u0645\u0631\u0636", "\u0623\u0645\u0631\u0627\u0636", "\u0635\u062d\u0629", "\u0635\u062d\u064a", "\u0637\u0628\u064a", "\u062d\u064a\u0648\u064a", "\u0628\u064a\u0648\u0644\u0648\u062c\u064a",
        "\u0646\u062a\u064a\u062c\u0629", "\u0646\u062a\u0627\u0626\u062c", "\u0628\u064a\u0627\u0646\u0627\u062a", "\u0645\u0646\u0635\u0629", "\u0628\u062d\u062b", "\u0645\u0635\u062f\u0631", "\u062a\u0631\u062a\u064a\u0628", "\u062a\u0642\u064a\u064a\u0645",
        "\u0627\u0634\u0631\u062d", "\u0641\u0633\u0631", "\u0642\u0627\u0631\u0646", "\u0645\u0627 \u0627\u0644\u0641\u0631\u0642", "\u0627\u0644\u0641\u0631\u0642 \u0628\u064a\u0646", "\u0643\u064a\u0641 \u064a\u0639\u0645\u0644",
        "\u0645\u0633\u0627\u0639\u062f\u0629", "\u0633\u0627\u0639\u062f\u0646\u064a", "\u0645\u0633\u0627\u0639\u062f\u062a\u064a", "\u0645\u0627\u0630\u0627 \u062a\u0633\u062a\u0637\u064a\u0639", "\u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0643", "\u0645\u0627 \u0647\u0648", "\u0645\u0627 \u0647\u064a",
    ]

    if any(k in q for k in allowed_keywords):
        return True

    has_arabic = any("\u0600" <= ch <= "\u06ff" for ch in q)
    looks_like_question = any(token in q for token in ["?", "\u061f", "what", "how", "why", "\u0645\u0627", "\u0643\u064a\u0641", "\u0647\u0644", "\u0644\u0645\u0627\u0630\u0627"])
    if has_arabic or looks_like_question or has_association_context:
        return True

    return False


def out_of_scope_response() -> str:
    return (
        _u("""
\u064a\u0645\u0643\u0646\u0646\u064a \u0627\u0644\u0645\u0633\u0627\u0639\u062f\u0629 \u0641\u064a \u0627\u0644\u0623\u0633\u0626\u0644\u0629 \u0627\u0644\u062a\u0639\u0644\u064a\u0645\u064a\u0629 \u0627\u0644\u0645\u062a\u0639\u0644\u0642\u0629 \u0628\u0627\u0644\u0648\u0631\u0627\u062b\u0629 \u0648\u0627\u0644\u0628\u064a\u0648\u0625\u0646\u0641\u0648\u0631\u0645\u0627\u062a\u0643\u0633 \u0648\u0627\u0644\u0635\u062d\u0629 \u0648\u0647\u0630\u0647 \u0627\u0644\u0645\u0646\u0635\u0629.
\u062c\u0631\u0628 \u0633\u0624\u0627\u0644\u0627\u064b \u0645\u062b\u0644: \u0643\u064a\u0641 \u062a\u0633\u0627\u0639\u062f\u0646\u064a\u061f \u0645\u0627 \u0647\u0648 SNP\u061f \u0627\u0634\u0631\u062d \u0644\u064a \u0647\u0630\u0647 \u0627\u0644\u0646\u062a\u064a\u062c\u0629\u060c \u0623\u0648 \u0645\u0627 \u0627\u0644\u0641\u0631\u0642 \u0628\u064a\u0646 GWAS \u0648 PRS\u061f
""").strip()
        + "\n\n"
        + safe_research_disclaimer()
    )


def build_strict_prompt(row: Optional[Dict[str, Any]], user_question: str = "") -> Dict[str, Any]:
    """Build controlled prompts for local Ollama while allowing broad educational questions."""
    has_association_context = isinstance(row, dict) and bool(row)
    context = extract_association_context(row or {}) if has_association_context else {}
    result_context = build_result_context_text(context) if has_association_context else "لا توجد نتيجة محددة مرفقة بالسؤال."
    glossary_context = get_glossary_context(row or {}) if has_association_context else get_general_glossary_context()

    user_prompt = f"""
السياق الموثوق:
{result_context}

قاموس المصطلحات:
{glossary_context if glossary_context else "لا يوجد سياق قاموس متاح."}

سؤال المستخدم:
{user_question.strip() if user_question.strip() else "اشرح النتيجة أو المفهوم للمستخدم."}

اكتب إجابة تعليمية واضحة ومباشرة. إذا كان هناك سياق نتيجة، اربط الشرح بها. إذا كان السؤال عاما، اشرح المفهوم أو طريقة المساعدة داخل المنصة.
""".strip()

    return {
        "system_prompt": get_system_prompt(),
        "user_prompt": user_prompt,
        "result_context": result_context,
        "glossary_context": glossary_context,
        "has_association_context": has_association_context,
    }


def get_ollama_models(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> List[str]:
    """Return locally installed Ollama model names."""
    url = base_url.rstrip("/") + "/api/tags"
    if not ollama_reachable(base_url):
        return []
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        return [
            str(item.get("name") or item.get("model") or "").strip()
            for item in payload.get("models", [])
            if str(item.get("name") or item.get("model") or "").strip()
        ]
    except Exception:
        return []


def detect_gemma_model(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> Optional[str]:
    """Prefer installed Gemma models, then fall back to the first installed model."""
    models = get_ollama_models(base_url=base_url)
    for preferred in GEMMA_MODEL_PREFERENCE:
        if preferred in models:
            return preferred
    for model in models:
        if "gemma" in model.lower():
            return model
    return models[0] if models else None


def select_best_ollama_model(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> Dict[str, Any]:
    """Use the configured active model when available; otherwise select a suitable installed model."""
    selected = None
    reason = "Selected from installed local Ollama models."
    try:
        from core.ai.model_manager import get_active_model

        selected = get_active_model()
        if selected:
            reason = "Using the active model configured in AI Model Management."
    except Exception:
        selected = None

    installed = get_ollama_models(base_url=base_url)
    if selected not in installed:
        selected = detect_gemma_model(base_url=base_url)
        reason = "Active model was unavailable; selected the best installed local model."

    return {
        "selected_model": selected,
        "reason": reason,
        "benchmarks": [],
    }


def call_ollama_model(
    system_prompt: str,
    user_prompt: str,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    model_name: Optional[str] = None,
    timeout: int = DEFAULT_OLLAMA_TIMEOUT,
) -> str:
    """Call local Ollama /api/chat with the selected model."""
    configured_model = None
    if not model_name:
        try:
            from core.ai.model_manager import get_active_model

            configured_model = get_active_model()
        except Exception:
            configured_model = None

    model = model_name or configured_model or detect_gemma_model(base_url=base_url) or DEFAULT_OLLAMA_MODEL_NAME
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "keep_alive": "10m",
        "options": DEFAULT_OLLAMA_OPTIONS,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    result = json.loads(raw)
    return str(result.get("message", {}).get("content", "")).strip()


def strip_model_artifacts(text: str) -> str:
    """Remove local model thinking/code wrappers before displaying the answer."""
    text = str(text or "")
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", text, flags=re.DOTALL).strip()
    return text.replace("```", "").strip()


def contains_unsafe_claims(text: str) -> bool:
    """Detect unsafe diagnosis or treatment claims while allowing disclaimers."""
    lowered = str(text or "").lower()
    unsafe_patterns = [
        "أنت مصاب",
        "انت مصاب",
        "لديك مرض",
        "تشخيصك هو",
        "يؤكد إصابتك",
        "يجب أن تتناول",
        "استخدم هذا الدواء",
        "جرعة",
        "يسبب المرض حتما",
        "you have ",
        "you are diagnosed",
        "this confirms diagnosis",
        "take medication",
        "treatment is",
    ]
    return any(pattern in lowered for pattern in unsafe_patterns)


def general_rule_based_explanation(user_question: str = "") -> str:
    """Safe deterministic answer for broad educational/platform questions."""
    answer = _u("""
يمكنني مساعدتك كمساعد تعليمي في البيوإنفورماتكس والوراثة داخل هذه المنصة. أستطيع شرح مفاهيم مثل SNP وGene وGWAS وPRS وp-value، وتوضيح معنى النتائج، ومساعدة المستخدم على فهم البيانات، مصادرها، قوة الدليل، وحدود استخدام النتائج.

إذا أرسلت نتيجة محددة من المنصة، يمكنني شرح المرض أو الجين أو المتغير الجيني المرتبط بها، وتفسير درجة الترتيب أو قوة الدليل بلغة مبسطة. وإذا كان سؤالك عاما، يمكنني تقديم شرح تعليمي عن المفهوم أو الفرق بين المصطلحات.
""").strip()
    return answer + "\n\n" + safe_research_disclaimer()


def fallback_rule_based_explanation(row: Dict[str, Any], user_question: str = "") -> str:
    """Safe deterministic fallback explanation for a selected association row."""
    context = extract_association_context(row or {})
    disease = context.get("disease", "غير متوفر")
    disease_ar = context.get("disease_arabic", "")
    disease_display = f"{disease} / {disease_ar}" if disease_ar else disease
    rsid = context.get("rsid", "غير متوفر")
    gene = context.get("gene", "غير متوفر")
    p_value = context.get("p_value", "غير متوفر")
    score = context.get("importance_score", "غير متوفر")
    rank_label = context.get("rank_label", "غير متوفر")
    population = context.get("population", "غير متوفر")
    study_title = context.get("study_title", "غير متوفر")
    pubmed_id = context.get("pubmed_id", "غير متوفر")

    explanation = f"""
### 1. ملخص النتيجة
تشير هذه النتيجة إلى ارتباط بحثي ضمن البيانات المتاحة بين المتغير الجيني **{rsid}** ومرض/صفة **{disease_display}**. يظهر الجين المرتبط أو القريب في السجل باسم **{gene}**.

### 2. معنى العناصر الأساسية
- **SNP/rsID:** معرف لمتغير جيني محدد، وهنا هو **{rsid}**.
- **Gene:** الجين المرتبط أو القريب من المتغير في بيانات الدراسة، وهنا **{gene}**.
- **p-value:** قيمة إحصائية تساعد على تقدير قوة الدليل، والقيمة المعروضة هي **{p_value}**.
- **Population:** العينة أو الخلفية السكانية في الدراسة، والقيمة المتاحة هي **{population}**.

### 3. تفسير قوة الدليل بحذر
تعرض المنصة درجة أهمية مقدارها **{score}** وتصنيفا هو **{rank_label}**. هذا لا يعني سببية مباشرة، بل يساعد في ترتيب الارتباطات حسب قواعد المنصة والبيانات المتاحة.

### 4. سياق الدراسة
عنوان الدراسة: **{study_title}**. PubMed ID: **{pubmed_id}**.

### 5. حدود الاستخدام
هذه النتيجة تعليمية وبحثية ولا تكفي وحدها لتقييم خطر فردي أو اتخاذ قرار طبي.
""".strip()
    return explanation + "\n\n" + safe_research_disclaimer()

def generate_ai_explanation(
    row: Optional[Dict[str, Any]],
    user_question: str = "",
    prefer_ollama: bool = True,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Hybrid explanation:"""
    has_input_association_context = isinstance(row, dict) and bool(row)

    if not is_question_in_scope(user_question, has_association_context=has_input_association_context):
        return {
            "mode": "scope_refusal",
            "model": model_name or "",
            "ollama_available": False,
            "gemma_available": False,
            "explanation": out_of_scope_response(),
            "used_fallback": True,
            "safety_replaced": False,
        }

    prompt_data = build_strict_prompt(row, user_question=user_question)
    has_association_context = bool(prompt_data.get("has_association_context"))

    ollama_available = False
    selected_model = model_name

    if prefer_ollama:
        model_selection = select_best_ollama_model(base_url=base_url)
        selected_model = selected_model or model_selection.get("selected_model")
        ollama_available = bool(get_ollama_models(base_url=base_url))

    if prefer_ollama and ollama_available and selected_model:
        try:
            ai_text = call_ollama_model(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=prompt_data["user_prompt"],
                base_url=base_url,
                model_name=selected_model,
            )

            ai_text = strip_model_artifacts(ai_text)

            if contains_unsafe_claims(ai_text):
                fallback = (
                    fallback_rule_based_explanation(row or {}, user_question=user_question)
                    if has_association_context
                    else general_rule_based_explanation(user_question=user_question)
                )

                return {
                    "mode": "rule_based_fallback_after_safety_check",
                    "model": selected_model,
                    "ollama_available": True,
                    "gemma_available": "gemma" in selected_model.lower(),
                    "explanation": fallback,
                    "used_fallback": True,
                    "safety_replaced": True,
                    "result_context": prompt_data["result_context"],
                    "glossary_context": prompt_data["glossary_context"],
                }

            if safe_research_disclaimer() not in ai_text:
                ai_text = ai_text.strip() + "\n\n" + safe_research_disclaimer()

            return {
                "mode": "ollama_local",
                "model": selected_model,
                "ollama_available": True,
                "gemma_available": "gemma" in selected_model.lower(),
                "explanation": ai_text,
                "used_fallback": False,
                "safety_replaced": False,
                "result_context": prompt_data["result_context"],
                "glossary_context": prompt_data["glossary_context"],
            }

        except Exception as exc:
            fallback = (
                fallback_rule_based_explanation(row or {}, user_question=user_question)
                if has_association_context
                else general_rule_based_explanation(user_question=user_question)
            )

            return {
                "mode": "rule_based_fallback_after_ollama_error",
                "model": selected_model,
                "ollama_available": True,
                "gemma_available": "gemma" in selected_model.lower(),
                "ollama_error": str(exc),
                "explanation": fallback,
                "used_fallback": True,
                "safety_replaced": False,
                "result_context": prompt_data["result_context"],
                "glossary_context": prompt_data["glossary_context"],
            }

    fallback = (
        fallback_rule_based_explanation(row or {}, user_question=user_question)
        if has_association_context
        else general_rule_based_explanation(user_question=user_question)
    )

    return {
        "mode": "rule_based_fallback",
        "model": selected_model or "",
        "ollama_available": ollama_available,
        "gemma_available": bool(selected_model and "gemma" in selected_model.lower()),
        "explanation": fallback,
        "used_fallback": True,
        "safety_replaced": False,
        "result_context": prompt_data["result_context"],
        "glossary_context": prompt_data["glossary_context"],
    }


def export_ai_explanation_test(row: Dict[str, Any], output_name: str = "ai_explanation_test.csv") -> Path:
    """Export one AI explanation test result for documentation."""
    result = generate_ai_explanation(row)

    outputs_dir = get_project_root() / "outputs" / "tables"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    output_path = outputs_dir / output_name

    export_row = {
        "mode": result.get("mode", ""),
        "model": result.get("model", ""),
        "ollama_available": result.get("ollama_available", ""),
        "used_fallback": result.get("used_fallback", ""),
        "safety_replaced": result.get("safety_replaced", ""),
        "explanation": result.get("explanation", ""),
    }

    pd.DataFrame([export_row]).to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path
