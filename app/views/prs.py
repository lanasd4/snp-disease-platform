
"""
PRS Prototype UI Components
"""

from __future__ import annotations

import streamlit as st

from app.ui.components import empty_state, notice, page_header, section_title, stat_card
from core.diseases import list_diseases
from core.i18n import is_rtl, tr


from core.prs import (
    load_active_ranked_results,
    get_available_diseases,
    normalize_prs_input_table,
    calculate_prs,
    build_prs_interpretation,
    validate_prs_input,
    build_prs_validation_report,
)


def render_prs_prototype_page():
    page_header(
        tr("نموذج المخاطر الجينية (PRS)", "Polygenic risk score (PRS) demo"),
        subtitle=tr("نموذج تعليمي يوضح كيف تُجمع آثار عدة متغيرات جينية في درجة واحدة.",
                    "An educational demo of how the effects of several variants are combined into one score."),
        icon="🧪",
    )
    notice(tr("للتعليم والبحث فقط: لا يُستخدم للتشخيص ولا للتنبؤ بخطر شخص حقيقي.",
              "Education and research only: not for diagnosis or predicting a real person's risk."), "warn")

    df = load_active_ranked_results()
    available = set(get_available_diseases(df)) if not df.empty else set()
    arabic = is_rtl()
    diseases = [d for d in list_diseases() if d.name_en in available]
    if not diseases:
        empty_state("🧪", tr("لا توجد بيانات كافية", "Not enough data"))
        return

    section_title(tr("1. اختر المرض وعدد المتغيرات", "1. Choose a disease and number of variants"))
    c1, c2 = st.columns([2, 1])
    with c1:
        disease = st.selectbox(tr("المرض", "Disease"), diseases, key="prs_selected_disease",
                               format_func=lambda d: f"{d.icon} {d.display_name(arabic)}")
    with c2:
        max_snps = st.slider(tr("عدد المتغيرات", "Number of variants"), 3, 15, 6, key="prs_max_snps")

    prs_input_df = normalize_prs_input_table(disease.name_en, max_snps=max_snps)
    if prs_input_df.empty:
        empty_state("🧪", tr("لا توجد متغيرات كافية لهذا المرض", "Not enough variants for this disease"))
        return

    section_title(tr("2. أدخل عدد نسخ الأليل المؤثر لكل متغير", "2. Enter the number of risk-allele copies"),
                  tr("0 = لا توجد نسخة، 1 = نسخة واحدة، 2 = نسختان", "0 = none, 1 = one copy, 2 = two copies"))
    dosages = []
    cols = st.columns(3)
    for i, row in prs_input_df.reset_index(drop=True).iterrows():
        with cols[i % 3], st.container(border=True):
            st.markdown(f"**`{row['rsid']}`** · {row['gene_symbol']}")
            st.caption(f"{tr('الأليل المؤثر', 'Risk allele')}: {row['risk_allele']} · "
                       f"{tr('الوزن', 'Weight')}: {float(row.get('prototype_weight', 0)):.3f}")
            dosages.append(st.segmented_control(
                tr("عدد النسخ", "Copies"), [0, 1, 2], default=0, key=f"prs_dosage_{i}_{row['rsid']}",
                label_visibility="collapsed") or 0)
    prs_input_df = prs_input_df.reset_index(drop=True)
    prs_input_df["genotype_dosage"] = dosages

    validation = validate_prs_input(prs_input_df)
    for error in validation["errors"]:
        st.error(error)

    section_title(tr("3. احسب الدرجة", "3. Calculate"))
    if not st.button(tr("احسب الدرجة", "Calculate score"), type="primary", icon="🧮",
                     key="calculate_prs_prototype", disabled=not validation["is_valid"]):
        _render_method_help()
        return

    result = calculate_prs(prs_input_df)
    m1, m2, m3 = st.columns(3)
    with m1:
        stat_card(tr("الدرجة الخام", "Raw score"), result["raw_score"], icon="Σ")
    with m2:
        stat_card(tr("الدرجة المعيارية", "Normalized"), f"{result['normalized_score']}%", icon="📈")
    with m3:
        stat_card(tr("المستوى التعليمي", "Educational level"), result["risk_level"], icon="🎯")

    with st.container(border=True):
        st.markdown(build_prs_interpretation(result, disease.name_en))

    report_df = build_prs_validation_report(result["details"], result)
    cols_shown = [c for c in ["rsid", "gene_symbol", "risk_allele", "prototype_weight", "genotype_dosage",
                              "prs_contribution"] if c in report_df.columns]
    st.dataframe(report_df[cols_shown], hide_index=True, width="stretch",
                 column_config={"rsid": "SNP", "gene_symbol": tr("الجين", "Gene"),
                                "risk_allele": tr("الأليل المؤثر", "Risk allele"),
                                "prototype_weight": tr("الوزن", "Weight"),
                                "genotype_dosage": tr("عدد النسخ", "Copies"),
                                "prs_contribution": tr("المساهمة", "Contribution")})
    st.download_button(tr("تحميل التقرير (CSV)", "Download report (CSV)"),
                       data=report_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="prs_prototype_report.csv", mime="text/csv", icon="⬇️", key="download_prs_report")
    _render_method_help()


METHOD_STEPS = [
    ("تُختار أقوى المتغيرات المرتبطة بالمرض.",
     "The disease's strongest variants are selected."),
    ("وزن كل متغير = حجم الأثر (Beta) أو لوغاريتم نسبة الأرجحية إن توفر، وإلا درجة الأهمية كبديل تعليمي.",
     "Each weight is the reported beta or log(odds ratio) when available, otherwise the importance score."),
    ("مساهمة المتغير = عدد النسخ × الوزن.",
     "A variant's contribution = copies × weight."),
    ("الدرجة = مجموع المساهمات، وتُعرض أيضًا كنسبة من أعلى قيمة ممكنة.",
     "The score is the sum, also shown as a share of the maximum possible."),
]


def _render_method_help():
    with st.expander(tr("كيف يتم الحساب؟", "How is it calculated?"), icon="ℹ️"):
        steps = [f"{i}. {tr(ar, en)}" for i, (ar, en) in enumerate(METHOD_STEPS, start=1)]
        st.markdown("\n".join(steps))
        st.caption(tr(
            "النماذج السريرية الحقيقية تستخدم آلاف المتغيرات وأوزانًا معايرة على مجموعات سكانية، لذلك هذه الدرجة للتوضيح فقط.",
            "Clinical PRS models use thousands of variants with population-calibrated weights, so this score is illustrative only.",
        ))
