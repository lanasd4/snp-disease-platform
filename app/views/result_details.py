
"""
Integrated Result Details Components
"""

from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st


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
        "importance_score": _first_available(data, ["importance_score", "score", "ranking_score"]),
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
    """Build a clear Arabic Markdown explanation for why the result received its score/rank."""
    p_value = row.get("p_value", "غير متوفر")
    score = row.get("importance_score", "غير متوفر")
    rank_label = row.get("rank_label", "غير متوفر")
    rank_label_ar = row.get("rank_label_arabic", "")
    risk_allele = row.get("risk_allele", "")
    odds_ratio = row.get("odds_ratio", "")
    effect_size = row.get("effect_size", "")
    population = row.get("population", "")
    study_title = row.get("study_title", "")
    pubmed_id = row.get("pubmed_id", "")

    reasons = []

    if p_value != "غير متوفر":
        reasons.append(
            f"قيمة الدلالة الإحصائية المتاحة هي **{p_value}**، وهي من الإشارات التي تستخدمها المنصة لتقدير قوة الدليل البحثي."
        )

    if score != "غير متوفر":
        reasons.append(
            f"درجة الأهمية المعروضة لهذه النتيجة هي **{score}**، وهي درجة ترتيب داخلية تساعد على مقارنة النتائج فيما بينها."
        )

    if rank_label != "غير متوفر":
        if rank_label_ar and rank_label_ar != "غير متوفر":
            label_text = f"{rank_label_ar} | {rank_label}"
        else:
            label_text = rank_label

        reasons.append(
            f"تصنيف قوة الارتباط لهذه النتيجة هو **{label_text}**."
        )

    if risk_allele and risk_allele != "غير متوفر":
        reasons.append(
            f"يتوفر في السجل أليل مؤثر أو مرتبط بالخطر وهو **{risk_allele}**، وهذا يجعل وصف النتيجة أكثر اكتمالًا."
        )

    if odds_ratio and odds_ratio != "غير متوفر":
        reasons.append(
            f"يتوفر Odds Ratio بقيمة **{odds_ratio}**، وهو حقل إحصائي يساعد في فهم اتجاه أو قوة الارتباط داخل الدراسة."
        )

    if effect_size and effect_size != "غير متوفر":
        reasons.append(
            f"يتوفر حجم تأثير أو Beta بقيمة **{effect_size}**، وهو مؤشر إضافي يمكن استخدامه في تفسير قوة الارتباط."
        )

    if population and population != "غير متوفر":
        reasons.append(
            f"يتوفر سياق سكاني أو عينة للدراسة: **{population}**."
        )

    if study_title and study_title != "غير متوفر":
        reasons.append(
            "وجود عنوان دراسة مرتبط بالنتيجة يساعد في تتبع مصدر الدليل البحثي."
        )

    if pubmed_id and pubmed_id != "غير متوفر":
        reasons.append(
            f"وجود معرّف PubMed **{pubmed_id}** يساعد في الرجوع إلى المصدر البحثي الأصلي."
        )

    if not reasons:
        reasons.append(
            "يعتمد ترتيب هذه النتيجة على الحقول المتاحة داخل ملف النتائج، لكن بعض تفاصيل الدليل غير مكتملة في هذا السجل."
        )

    markdown_lines = [f"- {item}" for item in reasons]
    markdown_lines.append("")
    markdown_lines.append("> تنبيه: درجة الترتيب مخصصة لتنظيم النتائج البحثية داخل المنصة، ولا تمثل تقييمًا طبيًا أو تشخيصيًا.")

    return chr(10).join(markdown_lines)


def render_glossary_terms(row: dict):
    """Render related glossary terms safely without exposing raw HTML tags."""

    st.markdown("#### المصطلحات المرتبطة")

    try:
        import html

        glossary_df = get_relevant_glossary_for_result(row)

        if glossary_df.empty:
            st.info("لا توجد مصطلحات مرتبطة متاحة حاليًا.")
            return


        def get_value(record, column):
            if column not in record:
                return "—"

            return _safe_value(
                record.get(column),
                default="—"
            )


        table_rows = []


        for _, record in glossary_df.iterrows():

            arabic_term = html.escape(
                get_value(record, "arabic_term")
            )

            english_term = html.escape(
                get_value(record, "term")
            )

            arabic_definition = html.escape(
                get_value(record, "arabic_definition")
            )

            safe_note = html.escape(
                get_value(record, "safe_note")
            )


            row_html = (
                '<tr>'
                f'<td class="glossary-ar-term" dir="rtl">{arabic_term}</td>'
                f'<td class="glossary-en-term" dir="ltr">{english_term}</td>'
                f'<td class="glossary-definition" dir="rtl">{arabic_definition}</td>'
                f'<td class="glossary-note" dir="auto">{safe_note}</td>'
                '</tr>'
            )

            table_rows.append(row_html)


        html_table = (
            '<div class="glossary-rtl-wrapper" dir="rtl">'
            '<table class="glossary-rtl-table">'
            '<thead>'
            '<tr>'
            '<th>المصطلح العربي</th>'
            '<th>English Term</th>'
            '<th>التعريف العربي</th>'
            '<th>ملاحظة</th>'
            '</tr>'
            '</thead>'
            '<tbody>'
            + ''.join(table_rows)
            + '</tbody>'
            '</table>'
            '</div>'
        )


        # Streamlit الحديثة
        if hasattr(st, "html"):
            st.html(html_table)

        # Fallback للإصدارات الأقدم
        else:
            st.markdown(
                html_table,
                unsafe_allow_html=True
            )


    except Exception as exc:
        st.warning(
            f"تعذر عرض المصطلحات المرتبطة: {exc}"
        )
def render_ai_explanation_for_result(row: dict, prefix: str):
    st.markdown("#### الشرح الذكي لهذه النتيجة")

    st.caption(
        "يشرح هذا القسم النتيجة المختارة اعتمادًا على بيانات المنصة وقاموس المصطلحات. "
        "لا يقدم تشخيصًا أو توصيات علاجية."
    )

    question = st.text_area(
        "سؤال اختياري عن هذه النتيجة",
        placeholder="مثال: اشرح معنى قيمة الدلالة الإحصائية ودرجة الأهمية في هذه النتيجة.",
        key=_key(prefix, "inline_ai_question", row)
    )

    if st.button(
        "توليد شرح لهذه النتيجة",
        width="stretch",
        key=_key(prefix, "inline_ai_button", row)
    ):
        with st.spinner("جاري توليد الشرح..."):
            result = generate_ai_explanation(
                row,
                user_question=question,
                prefer_ollama=True
            )

        mode = result.get("mode", "")

        if mode in {"gemma_ollama", "ollama_local"}:
            st.success("تم توليد الشرح باستخدام المساعد الذكي المحلي.")
        elif mode == "scope_refusal":
            st.warning("السؤال خارج نطاق الشرح البحثي للمنصة.")
        else:
            st.info("تم توليد الشرح باستخدام القواعد الآمنة المعتمدة داخل المنصة.")

        st.markdown(result.get("explanation", ""))


def render_study_summary_for_result(row: dict, prefix: str):
    st.markdown("#### ملخص الدراسة المرتبطة")

    st.caption(
        "يعتمد الملخص على الحقول المنظمة المتاحة داخل المنصة مثل عنوان الدراسة، PubMed ID، المرض، SNP، الجين، والسكان."
    )

    if st.button(
        "عرض ملخص الدراسة لهذه النتيجة",
        width="stretch",
        key=_key(prefix, "inline_study_button", row)
    ):
        try:
            summary = build_structured_study_summary(row)

            tab_ar, tab_en, tab_fields = st.tabs([
                "الملخص العربي",
                "English Summary",
                "الحقول"
            ])

            with tab_ar:
                st.markdown(summary["arabic_summary"])

            with tab_en:
                st.markdown(summary["english_summary"])

            with tab_fields:
                st.dataframe(
                    pd.DataFrame([summary["context"]]),
                    width="stretch",
                    hide_index=True
                )

        except Exception as exc:
            st.warning(f"تعذر إنشاء ملخص الدراسة لهذه النتيجة: {exc}")


