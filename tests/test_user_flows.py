"""
End-to-end user flows driven through Streamlit's AppTest (real app, real widgets).
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.auth as auth

ENTRY = str(Path(__file__).resolve().parents[1] / "app" / "main.py")
NAV = "main_navigation_display"


def _app(admin: bool = False) -> AppTest:
    at = AppTest.from_file(ENTRY, default_timeout=120)
    if admin:
        at.session_state["auth_user"] = {"user_id": 0, "username": "t", "role": "admin", "must_change_password": 0}
        at.session_state["auth_role"] = "admin"
    return at.run()


def _open(at: AppTest, page_index: int) -> AppTest:
    radio = at.sidebar.radio(key=NAV)
    return radio.set_value(radio.options[page_index]).run()


def _no_errors(at: AppTest):
    assert not at.exception, [e.value for e in at.exception]


def _markdown_text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


# --- Home -------------------------------------------------------------------

def test_home_shows_ten_disease_tiles():
    at = _app()
    _no_errors(at)
    tiles = [b for b in at.button if str(b.key).startswith("dz_btn_")]
    assert len(tiles) == 10


def test_clicking_a_disease_tile_opens_search_with_results():
    at = _app()
    at.button(key="dz_btn_9").click().run()  # Alzheimer's disease
    _no_errors(at)
    assert at.session_state["current_page_key"] == "Search"
    assert at.text_input(key="srch_query").value == "مرض الزهايمر"
    table = at.dataframe[0].value
    assert len(table) > 0 and "APOE" in set(table["gene"])


def test_home_search_box_routes_to_the_right_mode():
    at = _app()
    at.text_input(key="home_search_query").input("rs429358")
    at.button[0].click()  # form submit is the first button
    at = at.run()
    _no_errors(at)
    assert at.session_state["current_page_key"] == "Search"
    assert at.session_state["srch_mode"] == "snp"


# --- Search -------------------------------------------------------------------

@pytest.mark.parametrize("query, expected_gene", [("السكري", "TCF7L2"), ("Breast Cancer", None), ("الروماتيزم", None)])
def test_disease_search_returns_one_row_per_variant(query, expected_gene):
    at = _open(_app(), 1)
    at.text_input(key="srch_query").input(query).run()
    _no_errors(at)
    table = at.dataframe[0].value
    assert len(table) > 0
    assert table["rsid"].is_unique
    if expected_gene:
        assert expected_gene in set(table["gene"])


def test_unknown_query_shows_empty_state_not_an_error():
    at = _open(_app(), 1)
    at.text_input(key="srch_query").input("xyzxyz").run()
    _no_errors(at)
    assert len(at.dataframe) == 0
    assert "لا توجد نتائج" in _markdown_text(at)


def test_arab_only_filter_keeps_only_arab_rows():
    at = _open(_app(), 1)
    at.text_input(key="srch_query").input("قصور الغدة الدرقية")
    at.toggle(key="srch_arab").set_value(True)
    at = at.run()
    _no_errors(at)
    table = at.dataframe[0].value
    assert len(table) > 0 and set(table["arab"]) == {"✓"}


def test_quick_pick_fills_the_query():
    at = _open(_app(), 1)
    at.button_group(key="srch_pick_disease").set_value("قصور الغدة الدرقية").run()
    _no_errors(at)
    assert at.text_input(key="srch_query").value == "قصور الغدة الدرقية"


# --- Language -------------------------------------------------------------------

def test_switching_to_english_translates_the_menu():
    at = _app()
    at.sidebar.radio(key="lang_switch_radio").set_value("en").run()
    _no_errors(at)
    options = at.sidebar.radio(key=NAV).options
    assert any("Home" in o for o in options)
    assert not any("الرئيسية" in o for o in options)


# --- Other pages ------------------------------------------------------------------

def test_ai_explanation_general_question_works_without_ollama():
    at = _open(_app(), 3)
    at.text_area(key="aiexp_question").input("ما هو SNP؟")
    at.button(key="aiexp_go").click()
    at = at.run()
    _no_errors(at)
    assert len(_markdown_text(at)) > 200


def test_prs_calculation_runs():
    at = _open(_app(), 6)
    at.button(key="calculate_prs_prototype").click().run()
    _no_errors(at)
    assert any("prs_contribution" in str(df.value.columns.tolist()) for df in at.dataframe)


def test_ranking_page_switches_disease():
    at = _open(_app(), 2)
    _no_errors(at)
    box = at.selectbox(key="rank_disease")
    box.select_index(8).run()  # Alzheimer's disease
    _no_errors(at)
    top = next(df.value for df in at.dataframe if "gene" in df.value.columns)
    assert top.iloc[0]["gene"] in {"APOE", "TOMM40", "APOC1"}


# --- Accounts -------------------------------------------------------------------

def test_guest_cannot_reach_admin_page():
    at = _app()
    assert not any("الإدارة" in o for o in at.sidebar.radio(key=NAV).options)


def test_login_with_bootstrap_admin_shows_admin_page(monkeypatch):
    monkeypatch.setenv("SNP_ADMIN_USERNAME", "flow_admin")
    monkeypatch.setenv("SNP_ADMIN_PASSWORD", "flow-admin-pass-1")
    auth.ensure_bootstrap_admin()
    at = _app()
    at.sidebar.text_input(key="auth_username").input("flow_admin")
    at.sidebar.text_input(key="auth_password").input("flow-admin-pass-1")
    at.sidebar.button[0].click()
    at = at.run()
    _no_errors(at)
    assert at.session_state["auth_role"] == "admin"
    assert any("الإدارة" in o for o in at.sidebar.radio(key=NAV).options)


def test_wrong_password_is_rejected():
    at = _app()
    at.sidebar.text_input(key="auth_username").input("nobody_here")
    at.sidebar.text_input(key="auth_password").input("wrong-password")
    at.sidebar.button[0].click()
    at = at.run()
    assert at.session_state["auth_role"] == "guest"


# --- Shareable links ---------------------------------------------------------------

def test_deep_link_opens_search_with_query():
    at = AppTest.from_file(ENTRY, default_timeout=120)
    at.query_params["q"] = "rs429358"
    at.run()
    _no_errors(at)
    assert at.session_state["current_page_key"] == "Search"
    assert at.session_state["srch_mode"] == "snp"
    assert len(at.dataframe[0].value) > 0


def test_deep_link_to_page_and_bad_mode_are_handled():
    at = AppTest.from_file(ENTRY, default_timeout=120)
    at.query_params["page"] = "ranking"
    at.run()
    assert at.session_state["current_page_key"] == "Ranking"
    at = AppTest.from_file(ENTRY, default_timeout=120)
    at.query_params["q"] = "<script>"
    at.query_params["mode"] = "drop table"
    at.run()
    _no_errors(at)
    assert at.session_state["srch_mode"] in {"disease", "snp", "gene"}


def test_ranking_comparison_uses_the_chosen_diseases():
    at = _open(_app(), 2)
    at.multiselect(key="rank_compare").set_value(["Obesity", "Asthma", "Breast Cancer"]).run()
    _no_errors(at)
    summary = next(df.value for df in at.dataframe if "confirmed_share" in df.value.columns)
    assert len(summary) == 3
    at.multiselect(key="rank_compare").set_value(["Obesity"]).run()
    _no_errors(at)
    assert not any("confirmed_share" in df.value.columns for df in at.dataframe)
