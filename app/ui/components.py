"""
Shared Streamlit widgets used by every page.
"""

from __future__ import annotations

import sqlite3
from html import escape as _esc
from typing import Optional

import streamlit as st

from core.i18n import is_rtl, t
from core.paths import DATABASE_PATH, LOGO_FILE, STYLES_FILE

COUNTED_TABLES = ["Disease", "SNP", "Gene", "Study", "PopulationRegion", "Association"]

# Session keys used to move between pages (consumed by app/main.py).
NAV_TARGET_KEY = "nav_target_page"
SEARCH_REQUEST_KEY = "search_request"

RANK_TONES = {"Confirmed": "strong", "Strong": "good", "Suggestive": "mid", "Below threshold": "low"}


# ---------------------------------------------------------------------------
# Page chrome
# ---------------------------------------------------------------------------

def load_custom_css() -> None:
    """Inject app/ui/styles.css into the page."""
    if STYLES_FILE.exists():
        st.markdown(f"<style>{STYLES_FILE.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def render_sidebar_header() -> None:
    """Platform logo at the top of the sidebar."""
    if LOGO_FILE.exists():
        st.sidebar.image(str(LOGO_FILE), width="stretch")
    else:
        st.sidebar.markdown("### SNP-Disease Platform")


def page_header(title: str, arabic_title: str = "", subtitle: str = "", arabic_subtitle: str = "",
                icon: str = "") -> None:
    """Page title block shown at the top of every page."""
    shown_title = arabic_title if is_rtl() and arabic_title else title
    shown_subtitle = arabic_subtitle if is_rtl() and arabic_subtitle else subtitle
    icon_html = f'<div class="ph-icon">{_esc(icon)}</div>' if icon else ""
    subtitle_html = f'<p class="ph-subtitle">{_esc(shown_subtitle)}</p>' if shown_subtitle else ""

    st.markdown(
        f"""
        <div class="page-head">
            {icon_html}
            <div class="ph-text">
                <h1 class="ph-title">{_esc(shown_title)}</h1>
                {subtitle_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(text: str, hint: str = "") -> None:
    hint_html = f'<span class="sec-hint">{_esc(hint)}</span>' if hint else ""
    st.markdown(f'<div class="sec-title"><span>{_esc(text)}</span>{hint_html}</div>', unsafe_allow_html=True)


def stat_card(label: str, value, note: str = "", icon: str = "") -> None:
    icon_html = f'<div class="stat-icon">{_esc(icon)}</div>' if icon else ""
    st.markdown(
        f"""
        <div class="stat-card">
            {icon_html}
            <div class="stat-body">
                <div class="stat-value">{_esc(str(value))}</div>
                <div class="stat-label">{_esc(label)}</div>
                <div class="stat-note">{_esc(note)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, tone: str = "neutral") -> str:
    """HTML for a small colored label (use inside unsafe_allow_html markdown)."""
    return f'<span class="badge badge-{_esc(tone)}">{_esc(text)}</span>'


def rank_text(rank_label) -> str:
    """Translated evidence level (Confirmed / Strong / Suggestive / Below threshold)."""
    from core.evidence import tier_label

    label = tier_label(rank_label)
    key = {"Confirmed": "search.tier_confirmed", "Strong": "search.tier_strong",
           "Suggestive": "search.tier_suggestive", "Below threshold": "search.tier_below"}[label]
    return t(key)


def rank_badge(rank_label) -> str:
    from core.evidence import tier_label

    label = tier_label(rank_label)
    return badge(rank_text(label), RANK_TONES.get(label, "neutral"))


def empty_state(icon: str, title: str, text: str = "") -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="es-icon">{_esc(icon)}</div>
            <div class="es-title">{_esc(title)}</div>
            <div class="es-text">{_esc(text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def notice(text: str, tone: str = "info") -> None:
    """Soft callout box (info / warn / research)."""
    st.markdown(f'<div class="notice notice-{_esc(tone)}">{_esc(text)}</div>', unsafe_allow_html=True)


def render_footer() -> None:
    st.markdown(
        f"""
        <div class="app-footer">
            <div>{_esc(t('footer.tagline'))}</div>
            <div class="footer-disclaimer">{_esc(t('common.disclaimer_research_only'))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Cards (kept for pages that still use them)
# ---------------------------------------------------------------------------

def feature_card(icon: str, title: str, arabic_title: str, text: str) -> None:
    shown_title = arabic_title if is_rtl() and arabic_title else title
    st.markdown(
        f"""
        <div class="feature-card">
            <div class="feature-icon">{_esc(str(icon))}</div>
            <div class="feature-title">{_esc(str(shown_title))}</div>
            <div class="feature-text">{_esc(str(text))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

def go_to_page(page_key: str) -> None:
    """Switch to another page on the next run (handled by app/main.py)."""
    st.session_state[NAV_TARGET_KEY] = page_key
    st.rerun()


def open_search(query: str, mode: Optional[str] = None) -> None:
    """Open the Search page and run `query` (mode guessed when not given)."""
    st.session_state[SEARCH_REQUEST_KEY] = {"query": query, "mode": mode}
    go_to_page("Search")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def get_database_counts() -> dict:
    """Counts shown to users, taken from the live search data so admin merges show up at once."""
    counts = {table: 0 for table in COUNTED_TABLES}

    if DATABASE_PATH.exists():
        with sqlite3.connect(DATABASE_PATH) as conn:
            for table in COUNTED_TABLES:
                try:
                    counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0]
                except sqlite3.Error:
                    counts[table] = 0

    from core.search_engine import load_tri_search_data

    data = load_tri_search_data()
    if not data.empty:
        def distinct(column: str) -> int:
            if column not in data.columns:
                return 0
            values = data[column].astype(str).str.strip()
            return int(values[~values.isin(["", "nan", "None"])].nunique())

        counts.update(Disease=distinct("disease_id"), SNP=distinct("rsid"), Gene=distinct("gene_symbol"),
                      Study=distinct("pubmed_id") or distinct("study_title"), Association=int(len(data)))
    return counts


def format_count(value) -> str:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{value:,}"
