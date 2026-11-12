"""
SNP-Disease Platform - Streamlit entry point.

Run from the project root:
streamlit run app/main.py
"""

import sys
from pathlib import Path

# Make the project root importable so `app.*` and `core.*` resolve no matter
# how Streamlit was launched. This is the only sys.path change in the project.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from app.ui.components import (  # noqa: E402
    NAV_TARGET_KEY,
    SEARCH_REQUEST_KEY,
    load_custom_css,
    render_footer,
    render_sidebar_header,
)
from app.views.about import render_about_page  # noqa: E402
from app.views.admin import render_admin_dashboard_page  # noqa: E402
from app.views.ai_explanation import render_ai_explanation_page  # noqa: E402
from app.views.circos import render_circos_plot_page  # noqa: E402
from app.views.home import render_home_page  # noqa: E402
from app.views.prs import render_prs_prototype_page  # noqa: E402
from app.views.ranking import render_association_ranking_page  # noqa: E402
from app.views.search import render_disease_search_page  # noqa: E402
from app.views.study_summary import render_study_summary_page  # noqa: E402
from core.auth import (  # noqa: E402
    ensure_bootstrap_admin,
    ensure_user_account_table,
    init_auth_state,
    is_admin,
    render_auth_sidebar,
    render_force_password_change_gate,
    render_user_status_card,
)
from core.i18n import inject_direction_css, render_language_switch, t  # noqa: E402

st.set_page_config(
    page_title="SNP-Disease Platform",
    page_icon=str(PROJECT_ROOT / "app" / "assets" / "favicon.png"),
    layout="wide",
    initial_sidebar_state="auto",  # open on desktop, collapsed on phones
)

DEFAULT_PAGE = "Home"
ADMIN_PAGE = "Admin Dashboard"

# Internal page key -> (icon, i18n label key, render function).
# Keys are stable English identifiers, independent of the display language.
PAGES = {
    "Home": ("🏠", "nav.home", render_home_page),
    "Search": ("🔎", "nav.search", render_disease_search_page),
    "Ranking": ("📊", "nav.ranking", render_association_ranking_page),
    "AI Explanation": ("🧠", "nav.ai_explanation", render_ai_explanation_page),
    "Study Summaries": ("📄", "nav.study_summaries", render_study_summary_page),
    "Circos Plot": ("🧬", "nav.circos", render_circos_plot_page),
    "PRS Prototype": ("🧪", "nav.prs", render_prs_prototype_page),
    "About": ("ℹ️", "nav.about", render_about_page),
    ADMIN_PAGE: ("🛡️", "nav.admin", render_admin_dashboard_page),
}


def get_visible_page_keys() -> list:
    """Return the page keys the current user may see (admin page only for admins)."""
    return [key for key in PAGES if key != ADMIN_PAGE or is_admin()]


def page_display_label(page_key: str) -> str:
    """Icon + translated label shown in the sidebar for a page key."""
    icon, label_key, _ = PAGES[page_key]
    return f"{icon}  {t(label_key, default=page_key)}"


# URL slugs for shareable links, e.g. ?page=search&q=rs429358 or ?page=ranking
PAGE_SLUGS = {
    "home": "Home", "search": "Search", "ranking": "Ranking", "ai": "AI Explanation",
    "studies": "Study Summaries", "circos": "Circos Plot", "prs": "PRS Prototype", "about": "About",
}


def apply_deep_link() -> None:
    """On a session's first run, open the page / search named in the URL query string."""
    if st.session_state.get("_deep_link_applied"):
        return
    st.session_state["_deep_link_applied"] = True

    params = st.query_params
    query = (params.get("q") or "").strip()[:200]
    page = PAGE_SLUGS.get((params.get("page") or "").lower())
    if query:
        st.session_state[SEARCH_REQUEST_KEY] = {"query": query, "mode": params.get("mode") or None}
        page = "Search"
    if page:
        st.session_state[NAV_TARGET_KEY] = page


def render_navigation() -> str:
    """Render the sidebar page selector and return the selected page key."""
    visible_keys = get_visible_page_keys()
    labels = [page_display_label(key) for key in visible_keys]

    # A page asked to open another page (app.ui.components.go_to_page).
    target = st.session_state.pop(NAV_TARGET_KEY, None)
    if target in visible_keys:
        st.session_state["current_page_key"] = target
        st.session_state["main_navigation_display"] = labels[visible_keys.index(target)]

    current = st.session_state.get("current_page_key", DEFAULT_PAGE)
    if current not in visible_keys:
        current = DEFAULT_PAGE

    # Labels change with the language; keep the widget on the current page.
    if st.session_state.get("main_navigation_display") not in labels:
        st.session_state["main_navigation_display"] = labels[visible_keys.index(current)]

    st.sidebar.markdown(f"<div class='nav-caption'>{t('nav.menu')}</div>", unsafe_allow_html=True)
    selected_label = st.sidebar.radio(
        "Navigation",
        labels,
        label_visibility="collapsed",
        key="main_navigation_display",
    )
    page = visible_keys[labels.index(selected_label)]
    st.session_state["current_page_key"] = page
    return page


def main() -> None:
    load_custom_css()
    ensure_user_account_table()
    ensure_bootstrap_admin()
    init_auth_state()
    inject_direction_css()

    render_sidebar_header()
    apply_deep_link()
    page = render_navigation()

    st.sidebar.divider()
    render_language_switch()
    render_auth_sidebar()
    render_user_status_card()

    # Accounts flagged must_change_password (e.g. after an admin password
    # reset) see nothing but the password-change form.
    if render_force_password_change_gate():
        st.stop()

    if page == ADMIN_PAGE and not is_admin():
        st.error(t('common.admin_restricted'))
    else:
        _, _, render_page = PAGES[page]
        render_page()

    render_footer()


if __name__ == "__main__":
    main()
