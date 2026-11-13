
"""
Study Summary Engine
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
import pandas as pd
from core.paths import get_project_root


def _clean_value(value: Any, default: str = "غير متوفر") -> str:
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip()

    if not text or text.lower() in ["nan", "none", "null", "na", "n/a", ""]:
        return default

    return text


def _first_available(row: Dict[str, Any], candidates: List[str], default: str = "غير متوفر") -> str:
    if row is None:
        return default

    if not isinstance(row, dict):
        try:
            row = dict(row)
        except Exception:
            return default

    lower_map = {str(k).lower(): k for k in row.keys()}

    for candidate in candidates:
        c = candidate.lower()
        if c in lower_map:
            return _clean_value(row.get(lower_map[c]), default=default)

    for candidate in candidates:
        c = candidate.lower()
        for key_lower, original_key in lower_map.items():
            if c == key_lower or c in key_lower or key_lower in c:
                return _clean_value(row.get(original_key), default=default)

    return default


def extract_study_context(row: Dict[str, Any]) -> Dict[str, str]:
    """Extract available study-related fields from a result row."""
    if not isinstance(row, dict):
        try:
            row = dict(row)
        except Exception:
            row = {}

    return {
        "study_title": _first_available(row, ["study_title", "study", "title"]),
        "pubmed_id": _first_available(row, ["pubmed_id", "pmid", "pubmed"]),
        "publication_year": _first_available(row, ["publication_year", "year"]),
        "journal": _first_available(row, ["journal"]),
        "source_database": _first_available(row, ["source_database", "source"]),
        "disease": _first_available(row, ["disease_name", "disease", "trait", "mapped_trait"]),
        "disease_arabic": _first_available(row, ["disease_arabic_name", "disease_arabic", "arabic_name"], default=""),
        "rsid": _first_available(row, ["rsid", "rs_id", "snp", "snp_id", "variant_id"]),
        "gene": _first_available(row, ["gene_symbol", "gene", "mapped_gene"]),
        "p_value": _first_available(row, ["p_value", "p-value", "pvalue"]),
        "independent_gws_studies": _first_available(row, ["independent_gws_studies"], default="—"),
        "rank_label": _first_available(row, ["rank_label", "rank"]),
        "rank_label_arabic": _first_available(row, ["rank_label_arabic"], default=""),
        "population": _first_available(row, ["population", "population_label", "ancestry"]),
        "region": _first_available(row, ["region"]),
        "country": _first_available(row, ["country"]),
        "risk_allele": _first_available(row, ["risk_allele", "effect_allele"], default=""),
        "odds_ratio": _first_available(row, ["odds_ratio", "or"], default=""),
        "effect_size": _first_available(row, ["effect_size", "beta"], default=""),
        "arab_related": _first_available(row, ["arab_related", "is_arab_related", "regional_label"], default=""),
    }


def _format_disease(context: Dict[str, str]) -> str:
    disease = context.get("disease", "غير متوفر")
    disease_ar = context.get("disease_arabic", "")

    if disease_ar and disease_ar != "غير متوفر":
        return f"{disease} / {disease_ar}"

    return disease


def build_arabic_study_summary(row: Dict[str, Any]) -> str:
    """Generate a safe Arabic summary from available metadata."""
    c = extract_study_context(row)

    disease_display = _format_disease(c)

    summary = f"""
### ملخص الدراسة

تشير البيانات المتاحة في المنصة إلى وجود سجل بحثي مرتبط بمرض/صفة **{disease_display}**، ويتضمن المتغير الجيني **{c['rsid']}** المرتبط أو القريب من الجين **{c['gene']}**.

### معلومات الدراسة المتاحة

- **عنوان الدراسة:** {c['study_title']}
- **معرّف PubMed:** {c['pubmed_id']}
- **سنة النشر:** {c['publication_year']}
- **المجلة:** {c['journal']}
- **مصدر البيانات:** {c['source_database']}

### سياق العينة والدليل

- **السكان/العينة:** {c['population']}
- **المنطقة:** {c['region']}
- **الدولة:** {c['country']}
- **قيمة الدلالة الإحصائية p-value:** {c['p_value']}
- **مستوى الدليل في المنصة:** {c['rank_label_arabic'] or c['rank_label']}
- **دراسات مستقلة بلغت الدلالة:** {c['independent_gws_studies']}
""".strip()

    extra_lines = []

    if c["risk_allele"] and c["risk_allele"] != "غير متوفر":
        extra_lines.append(f"- **الأليل المرتبط بالخطر:** {c['risk_allele']}")

    if c["odds_ratio"] and c["odds_ratio"] != "غير متوفر":
        extra_lines.append(f"- **Odds Ratio:** {c['odds_ratio']}")

    if c["effect_size"] and c["effect_size"] != "غير متوفر":
        extra_lines.append(f"- **Effect size / Beta:** {c['effect_size']}")

    if c["arab_related"] and c["arab_related"] != "غير متوفر":
        extra_lines.append(f"- **مؤشر الارتباط العربي/الإقليمي:** {c['arab_related']}")

    if extra_lines:
        summary += "\n\n### حقول إضافية متاحة\n" + "\n".join(extra_lines)

    summary += """

### حدود الملخص

يعتمد هذا الملخص على الحقول المتاحة داخل المنصة فقط، مثل عنوان الدراسة، معرّف PubMed، المرض، المتغير الجيني، الجين، السكان، وقيم الدليل الإحصائي. لا يعني هذا الملخص أن النص الكامل للدراسة قد تم تحليله داخل المنصة.

تنبيه: هذه المعلومات لأغراض تعليمية وبحثية فقط، ولا تُستخدم للتشخيص الطبي أو اتخاذ قرارات علاجية.
""".strip()

    return summary


def build_english_study_summary(row: Dict[str, Any]) -> str:
    """Generate a safe English summary from available metadata."""
    c = extract_study_context(row)

    summary = f"""
### Study Summary

The available platform data indicates a research record related to **{c['disease']}**, involving the genetic variant **{c['rsid']}** and the gene **{c['gene']}**.

### Available Study Metadata

- **Study title:** {c['study_title']}
- **PubMed ID:** {c['pubmed_id']}
- **Publication year:** {c['publication_year']}
- **Journal:** {c['journal']}
- **Data source:** {c['source_database']}

### Evidence Context

- **Population:** {c['population']}
- **Region:** {c['region']}
- **Country:** {c['country']}
- **p-value:** {c['p_value']}
- **Platform evidence level:** {c['rank_label']}
- **Independent genome-wide significant studies:** {c['independent_gws_studies']}
""".strip()

    extra_lines = []

    if c["risk_allele"] and c["risk_allele"] != "غير متوفر":
        extra_lines.append(f"- **Risk allele:** {c['risk_allele']}")

    if c["odds_ratio"] and c["odds_ratio"] != "غير متوفر":
        extra_lines.append(f"- **Odds Ratio:** {c['odds_ratio']}")

    if c["effect_size"] and c["effect_size"] != "غير متوفر":
        extra_lines.append(f"- **Effect size / Beta:** {c['effect_size']}")

    if extra_lines:
        summary += "\n\n### Additional Available Fields\n" + "\n".join(extra_lines)

    summary += """

### Summary Limitations

This summary is based only on structured fields available inside the platform. It does not indicate that the full study text has been analyzed.

Notice: This information is for educational and research purposes only and must not be used for diagnosis or treatment decisions.
""".strip()

    return summary


def build_structured_study_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return both Arabic and English summaries with extracted metadata."""
    context = extract_study_context(row)

    return {
        "context": context,
        "arabic_summary": build_arabic_study_summary(row),
        "english_summary": build_english_study_summary(row),
    }


def load_active_ranked_results() -> pd.DataFrame:
    path = get_project_root() / "data" / "processed" / "ranked_associations_initial.csv"

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def export_study_summary_test(row: Dict[str, Any], output_name: str = "study_summary_test.csv") -> Path:
    result = build_structured_study_summary(row)

    outputs_dir = get_project_root() / "outputs" / "tables"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    output_path = outputs_dir / output_name

    context = result["context"]

    export_row = {
        **context,
        "arabic_summary": result["arabic_summary"],
        "english_summary": result["english_summary"],
    }

    pd.DataFrame([export_row]).to_csv(output_path, index=False, encoding="utf-8-sig")

    return output_path
