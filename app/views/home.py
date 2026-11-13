"""
Home page: hero with a direct search box, platform numbers, the disease catalogue and a short guide.
"""

import html

import streamlit as st

from app.ui.components import (
    feature_card,
    format_count,
    get_database_counts,
    go_to_page,
    open_search,
    section_title,
    stat_card,
)
from core.diseases import list_diseases
from core.i18n import is_rtl, t

TILES_PER_ROW = 5

# (icon, i18n title key, i18n text key, page to open)
FEATURES = [
    ("🔎", "home.f_search", "home.f_search_text", "Search"),
    ("📊", "home.f_ranking", "home.f_ranking_text", "Ranking"),
    ("🌍", "home.f_arab", "home.f_arab_text", "Search"),
    ("🧠", "home.f_ai", "home.f_ai_text", "AI Explanation"),
    ("📄", "home.f_summary", "home.f_summary_text", "Study Summaries"),
    ("🧬", "home.f_circos", "home.f_circos_text", "Circos Plot"),
    ("🧪", "home.f_prs", "home.f_prs_text", "PRS Prototype"),
    ("📚", "home.f_sources", "home.f_sources_text", "About"),
]


def _render_hero() -> None:
    # The logo is already at the top of the sidebar; the hero uses the full width.
    st.markdown(
        f"""
        <div class="hero">
            <span class="hero-kicker">{html.escape(t('home.kicker'))}</span>
            <h1>{html.escape(t('home.title'))}</h1>
            <p>{html.escape(t('home.subtitle'))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_numbers() -> None:
    counts = get_database_counts()
    numbers = [
        ("🩺", t('home.diseases'), counts.get("Disease", 0), t('home.diseases_note')),
        ("🧬", t('home.snps'), counts.get("SNP", 0), t('home.snps_note')),
        ("🔗", t('home.associations'), counts.get("Association", 0), t('home.associations_note')),
        ("📚", t('home.studies'), counts.get("Study", 0), t('home.studies_note')),
    ]
    for col, (icon, label, value, note) in zip(st.columns(len(numbers)), numbers):
        with col:
            stat_card(label, format_count(value), note, icon)


def _render_diseases() -> None:
    section_title(t('home.diseases_section'), t('home.diseases_hint'))
    arabic = is_rtl()
    diseases = list_diseases()

    for start in range(0, len(diseases), TILES_PER_ROW):
        row = diseases[start:start + TILES_PER_ROW]
        for col, disease in zip(st.columns(TILES_PER_ROW), row):
            with col, st.container(key=f"dz_{disease.disease_id}", border=True):
                st.markdown(
                    f"""
                    <div class="dz-icon">{html.escape(disease.icon)}</div>
                    <div class="dz-name">{html.escape(disease.display_name(arabic))}</div>
                    <div class="dz-desc">{html.escape(disease.description(arabic))}</div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(t('home.explore'), key=f"dz_btn_{disease.disease_id}", width="stretch"):
                    open_search(disease.display_name(arabic), mode="disease")


def _render_how_it_works() -> None:
    section_title(t('home.how_title'))
    steps = [("1", "home.step1", "home.step1_text"), ("2", "home.step2", "home.step2_text"),
             ("3", "home.step3", "home.step3_text")]
    for col, (num, title_key, text_key) in zip(st.columns(len(steps)), steps):
        with col:
            st.markdown(
                f"""
                <div class="feature-card">
                    <div class="step-num">{num}</div>
                    <div class="feature-title">{html.escape(t(title_key))}</div>
                    <div class="feature-text">{html.escape(t(text_key))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_features() -> None:
    section_title(t('home.features_title'))
    per_row = 4
    for start in range(0, len(FEATURES), per_row):
        row = FEATURES[start:start + per_row]
        for col, (icon, title_key, text_key, page) in zip(st.columns(per_row), row):
            with col:
                feature_card(icon, t(title_key), t(title_key), t(text_key))
                if st.button(t('home.open'), key=f"feature_{title_key}", type="tertiary"):
                    go_to_page(page)


def render_home_page() -> None:
    _render_hero()
    _render_numbers()
    _render_diseases()
    _render_how_it_works()
    _render_features()
