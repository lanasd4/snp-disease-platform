
"""
Integrated Result Details Components
"""

from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st


from core.auth import is_admin
from core.i18n import is_rtl, tr
from core.glossary import get_relevant_glossary_for_result
from core.ai.agent import generate_ai_explanation
from core.study_summary import build_structured_study_summary


def _safe_value(value, default: str = "غير متوفر") -> str:
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


def _first_available(data: dict, keys: list[str], default: str = "غير متوفر") -> str:
    if not isinstance(data, dict):
        return default

    lower_map = {str(k).lower(): k for k in data.keys()}

    for key in keys:
        key_lower = key.lower()

        if key_lower in lower_map:
            return _safe_value(data.get(lower_map[key_lower]), default)

    for key in keys:
        key_lower = key.lower()

        for existing_lower, original_key in lower_map.items():
            if key_lower == existing_lower or key_lower in existing_lower or existing_lower in key_lower:
                return _safe_value(data.get(original_key), default)

    return default


def normalize_result_context(raw_context: dict) -> dict:
    """Convert locals()/row data into a stable result dictionary."""
    data = dict(raw_context or {})

    return {
        "rsid": _first_available(data, ["rsid", "rs_id", "snp", "snp_id"]),
        "gene_symbol": _first_available(data, ["gene_symbol", "gene", "mapped_gene"]),
        "disease_name": _first_available(data, ["disease_name", "disease", "trait", "mapped_trait"]),
        "disease_arabic_name": _first_available(data, ["disease_arabic_name", "disease_arabic", "arabic_name"], default=""),
        "p_value": _first_available(data, ["p_value", "p-value", "pvalue"]),
        "evidence_tier": _first_available(data, ["evidence_tier"], default=""),
        "independent_gws_studies": _first_available(data, ["independent_gws_studies"], default=""),
        "independent_studies": _first_available(data, ["independent_studies"], default=""),
        "best_p_value": _first_available(data, ["best_p_value"], default=""),
        "max_sample_size": _first_available(data, ["max_sample_size"], default=""),
        "rank_label": _first_available(data, ["rank_label", "rank"]),
        "rank_label_arabic": _first_available(data, ["rank_label_arabic"], default=""),
        "risk_allele": _first_available(data, ["risk_allele", "effect_allele"], default=""),
        "odds_ratio": _first_available(data, ["odds_ratio", "or"], default=""),
        "effect_size": _first_available(data, ["effect_size", "beta"], default=""),
        "population": _first_available(data, ["population", "population_label", "ancestry"], default=""),
        "region": _first_available(data, ["region"], default=""),
        "country": _first_available(data, ["country"], default=""),
        "study_title": _first_available(data, ["study_title", "study", "title"], default=""),
        "pubmed_id": _first_available(data, ["pubmed_id", "pmid", "pubmed"], default=""),
        "publication_year": _first_available(data, ["publication_year", "year"], default=""),
        "journal": _first_available(data, ["journal"], default=""),
        "source_database": _first_available(data, ["source_database", "source"], default=""),
        "arab_related": _first_available(data, ["arab_related", "is_arab_related", "regional_label"], default=""),
    }


def _key(prefix: str, suffix: str, row: dict) -> str:
    rsid = row.get("rsid", "unknown")
    gene = row.get("gene_symbol", "gene")
    base = f"{prefix}_{rsid}_{gene}_{suffix}"
    digest = hashlib.md5(base.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{prefix}_{suffix}_{digest}"


def build_ranking_reason(row: dict) -> str:
    """Markdown explaining the association's evidence level, in the active language."""
    from core.evidence import GENOME_WIDE_P, arabic_studies, tier_label, tier_number

    def num(key):
        try:
            return float(str(row.get(key, "")).replace(",", ""))
        except ValueError:
            return None

    tier = tier_number(row.get("evidence_tier") if row.get("evidence_tier") not in ("", None) else row.get("rank_label"))
    gws, total, n, best_p = num("independent_gws_studies"), num("independent_studies"), num("max_sample_size"), num("best_p_value")
    level = tier_label(tier, arabic=is_rtl())
    lines = [tr(f"**مستوى الدليل: {level}**", f"**Evidence level: {level}**")]

    if tier == 3:
        lines.append(tr(f"بلغ الارتباط الدلالة على مستوى الجينوم (p < 5×10⁻⁸) في **{arabic_studies(gws)}** "
                        "منشورة في كتالوج GWAS، أي أنه تكرر ولم يظهر في دراسة واحدة فقط.",
                        f"The association reached genome-wide significance (p < 5×10⁻⁸) in **{int(gws)} independent "
                        "studies** in the GWAS Catalog, so it has been replicated."))
    elif tier == 2:
        lines.append(tr("بلغ الارتباط الدلالة على مستوى الجينوم (p < 5×10⁻⁸) في **دراسة واحدة**، ولم يتكرر بعد "
                        "في دراسة مستقلة أخرى.",
                        "The association reached genome-wide significance (p < 5×10⁻⁸) in **one study** and has "
                        "not yet been replicated in an independent study."))
    elif tier == 1:
        lines.append(tr("الدلالة مقترحة (p < 10⁻⁵) لكنها لم تبلغ عتبة الجينوم.",
                        "The signal is suggestive (p < 10⁻⁵) but below genome-wide significance."))
    else:
        lines.append(tr("لا تبلغ قيمة p عتبة الدلالة المعتمدة.", "The p-value does not reach the accepted threshold."))

    details = []
    if best_p is not None:
        details.append(tr(f"أفضل قيمة p في الكتالوج: **{best_p:.1e}**", f"Best p-value in the catalog: **{best_p:.1e}**"))
    if total:
        details.append(tr(f"عدد الدراسات التي ذكرته: **{int(total)}**", f"Studies reporting it: **{int(total)}**"))
    if n:
        details.append(tr(f"أكبر عينة: **{int(n):,}** مشارك", f"Largest sample: **{int(n):,}** participants"))
    effect = row.get("odds_ratio") or row.get("effect_size")
    if effect and effect != "غير متوفر":
        details.append(tr(f"حجم التأثير (OR أو Beta): **{effect}**", f"Effect size (OR or beta): **{effect}**"))
    lines += [f"- {d}" for d in details]
    lines.append("")
    lines.append(tr(f"تُرتّب النتائج حسب قوة الدلالة (أفضل قيمة p)، ويبيّن المستوى موثوقية الارتباط. "
                    f"العتبة {GENOME_WIDE_P:g} هي المعيار المعتمد في دراسات GWAS.",
                    f"Results are ordered by statistical strength (best p-value); the level shows reliability. "
                    f"The {GENOME_WIDE_P:g} threshold is the standard used in GWAS."))
    lines.append("")
    lines.append(tr("> مستوى الدليل يصف قوة الارتباط الإحصائي في الأبحاث، ولا يمثل تقييمًا طبيًا أو تشخيصيًا.",
                    "> The evidence level describes statistical evidence in research; it is not a medical or "
                    "diagnostic assessment."))
    return chr(10).join(lines)


def render_glossary_terms(row: dict):
    """Related glossary terms in the active language (term + definition + safety note)."""
    import html

    st.markdown(f"#### {tr('المصطلحات المرتبطة', 'Related terms')}")
    try:
        glossary_df = get_relevant_glossary_for_result(row)
    except Exception as exc:
        st.warning(f"{tr('تعذر عرض المصطلحات المرتبطة', 'Could not show related terms')}: {exc}")
        return
    if glossary_df.empty:
        st.info(tr("لا توجد مصطلحات مرتبطة متاحة حاليًا.", "No related terms available."))
        return

    arabic = is_rtl()

    def get_value(record, column):
        return html.escape(_safe_value(record.get(column), default="—")) if column in record else "—"

    rows = []
    for _, record in glossary_df.iterrows():
        term = get_value(record, "arabic_term" if arabic else "term")
        other = get_value(record, "term" if arabic else "arabic_term")
        definition = get_value(record, "arabic_definition" if arabic else "english_definition")
        note = get_value(record, "safe_note") if arabic else ""
        rows.append(f"<tr><td><b>{term}</b><br><span class='muted'>{other}</span></td>"
                    f"<td>{definition}</td>" + (f"<td>{note}</td>" if arabic else "") + "</tr>")
    direction = "rtl" if arabic else "ltr"
    headers = [tr("المصطلح", "Term"), tr("التعريف", "Definition")] + ([tr("ملاحظة", "Note")] if arabic else [])
    table = (f'<div class="glossary-rtl-wrapper" dir="{direction}"><table class="glossary-rtl-table"><thead><tr>'
             + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(rows)
             + "</tbody></table></div>")
    st.html(table)


def render_ai_explanation_for_result(row: dict, prefix: str):
    st.markdown(f"#### {tr('الشرح الذكي لهذه النتيجة', 'AI explanation of this result')}")
    st.caption(tr(
        "يشرح هذا القسم النتيجة المختارة اعتمادًا على بيانات المنصة وقاموس المصطلحات. لا يقدم تشخيصًا أو توصيات علاجية.",
        "Explains the selected result using the platform's data and glossary. No diagnosis or treatment advice.",
    ))
    question = st.text_area(
        tr("سؤال اختياري عن هذه النتيجة", "Optional question about this result"),
        placeholder=tr("مثال: اشرح معنى قيمة الدلالة الإحصائية ومستوى الدليل في هذه النتيجة.",
                       "e.g. Explain the p-value and the evidence level of this result."),
        key=_key(prefix, "inline_ai_question", row),
    )
    if st.button(tr("توليد شرح لهذه النتيجة", "Explain this result"), width="stretch",
                 key=_key(prefix, "inline_ai_button", row)):
        with st.spinner(tr("جاري توليد الشرح...", "Generating the explanation...")):
            result = generate_ai_explanation(row, user_question=question, prefer_ollama=True)
        mode = result.get("mode", "")
        if mode == "scope_refusal":
            st.warning(tr("السؤال خارج نطاق الشرح البحثي للمنصة.", "This question is outside the platform's scope."))
        elif not is_admin():
            pass
        elif mode in {"gemma_ollama", "ollama_local"}:
            st.success(tr("تم توليد الشرح باستخدام المساعد الذكي المحلي.", "Generated with the local AI assistant."))
        else:
            st.info(tr("تم توليد الشرح باستخدام القواعد الآمنة المعتمدة داخل المنصة.",
                       "Generated with the platform's built-in safe rules (AI model not available)."))
        st.markdown(result.get("explanation", ""))


def render_study_summary_for_result(row: dict, prefix: str):
    st.markdown(f"#### {tr('ملخص الدراسة المرتبطة', 'Summary of the related study')}")
    st.caption(tr(
        "يعتمد الملخص على الحقول المنظمة المتاحة داخل المنصة مثل عنوان الدراسة، PubMed ID، المرض، SNP، الجين، والسكان.",
        "Built from the platform's structured fields: study title, PubMed ID, disease, SNP, gene and population.",
    ))
    if st.button(tr("عرض ملخص الدراسة لهذه النتيجة", "Show the study summary"), width="stretch",
                 key=_key(prefix, "inline_study_button", row)):
        try:
            summary = build_structured_study_summary(row)
        except Exception as exc:
            st.warning(f"{tr('تعذر إنشاء ملخص الدراسة', 'Could not build the study summary')}: {exc}")
            return
        st.markdown(summary["arabic_summary"] if is_rtl() else summary["english_summary"])
        with st.expander(tr("الحقول المستخدمة", "Fields used")):
            st.dataframe(pd.DataFrame([summary["context"]]), width="stretch", hide_index=True)
