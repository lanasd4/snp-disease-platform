"""
Study summary page: a structured summary of the study behind one association.
"""

from __future__ import annotations

import html

import streamlit as st

from app.ui.components import empty_state, notice, page_header, section_title
from app.ui.pickers import pick_association
from core.i18n import is_rtl, tr
from core.study_summary import build_structured_study_summary

KEY = "studysum"
FROM_SEARCH_KEY = "study_selected_result_from_search"


def _fact(label: str, value) -> str:
    text = "—" if value in (None, "") or str(value).lower() == "nan" else str(value)
    return (f'<div class="fact"><div class="fact-label">{html.escape(label)}</div>'
            f'<div class="fact-value">{html.escape(text)}</div></div>')


def render_study_summary_page() -> None:
    page_header(
        tr("ملخص الدراسات", "Study summaries"),
        subtitle=tr("ملخص منظم للدراسة العلمية التي تقف خلف كل ارتباط: العنوان، المجلة، العينة، وقوة الدليل.",
                    "A structured summary of the study behind each association: title, journal, sample and evidence."),
        icon="📄",
    )

    section_title(tr("اختر الارتباط", "Choose an association"))
    row = pick_association(KEY, FROM_SEARCH_KEY)
    if not row:
        empty_state("📄", tr("لا توجد نتيجة مختارة", "No result selected"),
                    tr("اختر مرضًا ثم ارتباطًا لعرض ملخص دراسته.", "Pick a disease and an association to see its study."))
        return

    summary = build_structured_study_summary(row)
    pubmed = str(row.get("pubmed_id") or "").split(".")[0]

    section_title(tr("الدراسة", "The study"))
    with st.container(border=True):
        st.markdown(f"#### {html.escape(str(row.get('study_title') or '—'))}")
        st.markdown(
            f"""<div class="fact-grid">
            {_fact(tr('المجلة', 'Journal'), row.get('journal'))}
            {_fact(tr('سنة النشر', 'Year'), str(row.get('publication_year') or '').split('.')[0])}
            {_fact('PubMed', pubmed)}
            {_fact(tr('السكان المدروسون', 'Population'), row.get('population_label'))}
            </div>""",
            unsafe_allow_html=True,
        )
        if pubmed.isdigit():
            st.link_button(tr("فتح الدراسة على PubMed", "Open on PubMed"),
                           f"https://pubmed.ncbi.nlm.nih.gov/{pubmed}/", icon="🔗")

    section_title(tr("الملخص", "Summary"))
    first, second = ("arabic_summary", "english_summary") if is_rtl() else ("english_summary", "arabic_summary")
    tab_main, tab_other, tab_fields = st.tabs([
        tr("الملخص بالعربية", "English summary"),
        tr("English summary", "الملخص بالعربية"),
        tr("الحقول المستخرجة", "Extracted fields"),
    ])
    with tab_main:
        st.markdown(summary[first])
    with tab_other:
        st.markdown(summary[second])
    with tab_fields:
        st.dataframe(summary["context"], width="stretch")

    st.download_button(
        tr("تحميل الملخص", "Download summary"),
        data=f"{summary['arabic_summary']}\n\n---\n\n{summary['english_summary']}",
        file_name=f"study_summary_{row.get('rsid', 'result')}.txt",
        mime="text/plain",
        icon="⬇️",
        key=f"{KEY}_download",
    )
    notice(tr("الملخص مبني على البيانات المنظمة في المنصة ولا يغني عن قراءة الدراسة الأصلية.",
              "This summary is built from the platform's structured data and does not replace the original paper."),
           "research")
