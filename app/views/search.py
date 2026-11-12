"""
Search page: disease / SNP / gene search over the ranked associations.
"""

from __future__ import annotations

import html
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from app.ui.components import (
    SEARCH_REQUEST_KEY,
    empty_state,
    go_to_page,
    page_header,
    rank_badge,
    rank_text,
    section_title,
)
from app.views.result_details import (
    build_ranking_reason,
    normalize_result_context,
    render_ai_explanation_for_result,
    render_glossary_terms,
    render_study_summary_for_result,
)
from core.auth import clear_my_search_history, get_current_user, get_my_search_history, save_user_search_history
from core.diseases import list_diseases, resolve_disease
from core.i18n import is_rtl, t
from core.search_engine import search_tri_ranked_file

KEY = "srch"  # widget-key namespace for this page
MODES = ["disease", "snp", "gene"]
MODE_KEY, QUERY_KEY = f"{KEY}_mode", f"{KEY}_query"
RANK_LABELS = ["Very High", "High", "Moderate", "Low"]
SORTS = ["score", "pvalue", "studies", "gene"]
EXAMPLES = {
    "snp": ["rs7903146", "rs429358", "rs9939609", "rs2476601", "rs1801282"],
    "gene": ["TCF7L2", "APOE", "FTO", "HLA-DRB1", "BRCA2", "PTPN22"],
}
HISTORY_LIMIT = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def guess_mode(query: str) -> str:
    """rsID -> snp, known disease name -> disease, otherwise gene."""
    text = (query or "").strip()
    if re.fullmatch(r"rs\d+", text, flags=re.IGNORECASE):
        return "snp"
    if resolve_disease(text):
        return "disease"
    if re.fullmatch(r"[A-Za-z0-9-]{2,15}", text):
        return "gene"
    return "disease"


def _text(value, default: str = "—") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return default if not text or text.lower() in {"nan", "none", "null"} else text


def _format_p(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    return f"{number:.1e}" if number < 0.001 else f"{number:.4f}"


def _disease_label(row) -> str:
    return _text(row.get("disease_arabic_name")) if is_rtl() else _text(row.get("disease_name"))


# ---------------------------------------------------------------------------
# State and pending requests (from Home or other pages)
# ---------------------------------------------------------------------------

def _init_state() -> None:
    st.session_state.setdefault(MODE_KEY, "disease")
    st.session_state.setdefault(QUERY_KEY, "")
    st.session_state.setdefault(f"{KEY}_history", [])

    request = st.session_state.pop(SEARCH_REQUEST_KEY, None)
    if request and request.get("query"):
        mode = request.get("mode")
        st.session_state[MODE_KEY] = mode if mode in MODES else guess_mode(request["query"])
        st.session_state[QUERY_KEY] = request["query"]


def _set_query(query: str) -> None:
    """Callback for history buttons (runs before widgets are rebuilt)."""
    st.session_state[QUERY_KEY] = query


def _apply_pick(pill_key: str) -> None:
    """Callback for the quick-pick pills: copy the chosen value into the search box."""
    value = st.session_state.get(pill_key)
    if value:
        st.session_state[QUERY_KEY] = value


# ---------------------------------------------------------------------------
# Search panel
# ---------------------------------------------------------------------------

def _render_search_panel() -> dict:
    with st.container(key="search_panel"):
        # The control is laid out left-to-right (styles.css keeps its joined
        # corners correct), so in Arabic the options are reversed to keep
        # "disease" first on the right.
        st.segmented_control(
            t('search.type'),
            MODES[::-1] if is_rtl() else MODES,
            format_func=lambda m: t(f'search.mode_{m}'),
            key=MODE_KEY,
            label_visibility="collapsed",
        )
        # Clicking the active segment deselects it; treat that as "disease".
        mode = st.session_state.get(MODE_KEY) or "disease"

        st.text_input(
            t(f'search.input_{mode}'),
            placeholder=t(f'search.placeholder_{mode}'),
            key=QUERY_KEY,
        )

        if mode == "disease":
            arabic = is_rtl()
            icons = {d.display_name(arabic): d.icon for d in list_diseases()}
            picks = list(icons)
        else:
            icons, picks = {}, EXAMPLES[mode]
        # Pills wrap onto several lines, so they stay compact on phones.
        st.pills(
            t('search.quick_picks'),
            picks,
            format_func=lambda value: f"{icons.get(value, '')} {value}".strip(),
            key=f"{KEY}_pick_{mode}",
            on_change=_apply_pick,
            args=(f"{KEY}_pick_{mode}",),
        )

        with st.expander(t('search.advanced'), icon="⚙️"):
            c1, c2, c3 = st.columns(3)
            with c1:
                arab_only = st.toggle(t('search.arab_only'), key=f"{KEY}_arab")
                rank_labels = st.multiselect(t('search.rank_label'), RANK_LABELS, format_func=rank_text,
                                             key=f"{KEY}_ranks")
            with c2:
                min_score = st.slider(t('search.min_score'), 0, 100, 0, step=5, key=f"{KEY}_min_score")
                max_p = st.select_slider(
                    t('search.max_p_value'),
                    options=["5e-8", "1e-10", "1e-20", "1e-50", "1e-100"],
                    value="5e-8",
                    key=f"{KEY}_max_p",
                )
            with c3:
                sort = st.selectbox(t('search.sort_by'), SORTS, format_func=lambda s: t(f'search.sort_{s}'),
                                    key=f"{KEY}_sort")
                limit = st.slider(t('search.result_count'), 10, 200, 50, step=10, key=f"{KEY}_limit")
                gene_filter = ""
                if mode != "gene":
                    gene_filter = st.text_input(t('search.gene_label'), placeholder="TCF7L2",
                                                key=f"{KEY}_gene_filter")

    return {
        "mode": mode,
        "query": st.session_state.get(QUERY_KEY, "").strip(),
        "arab_only": arab_only,
        "rank_labels": rank_labels,
        "min_score": float(min_score),
        "max_p": float(max_p),
        "sort": sort,
        "limit": int(limit),
        "gene_filter": gene_filter.strip(),
    }


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def _apply_filters(df: pd.DataFrame, opts: dict) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["_score"] = pd.to_numeric(df.get("importance_score"), errors="coerce").fillna(0)
    df["_p"] = pd.to_numeric(df.get("p_value"), errors="coerce")
    df["_studies"] = pd.to_numeric(df.get("study_count_for_disease_snp"), errors="coerce").fillna(0)

    if opts["rank_labels"]:
        df = df[df["rank_label"].isin(opts["rank_labels"])]
    if opts["gene_filter"]:
        df = df[df["gene_symbol"].astype(str).str.contains(opts["gene_filter"], case=False, na=False, regex=False)]
    df = df[df["_score"] >= opts["min_score"]]
    df = df[df["_p"].isna() | (df["_p"] <= opts["max_p"])]

    # One row per variant and disease: keep its strongest evidence record
    # (the record count is already in study_count_for_disease_snp).
    df = df.sort_values(["_score", "_p"], ascending=[False, True], na_position="last")
    df = df.drop_duplicates(subset=["rsid", "disease_name"], keep="first")

    sort_by = {"score": (["_score", "_p"], [False, True]), "pvalue": (["_p"], [True]),
               "studies": (["_studies", "_score"], [False, False]), "gene": (["gene_symbol"], [True])}[opts["sort"]]
    return df.sort_values(sort_by[0], ascending=sort_by[1], na_position="last").reset_index(drop=True)


def _table(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "rsid": df["rsid"],
        "gene": df["gene_symbol"],
        "disease": [_disease_label(row) for _, row in df.iterrows()],
        "score": df["_score"],
        "rank": [rank_text(label) for label in df["rank_label"]],
        "p": [_format_p(v) for v in df["p_value"]],
        "studies": df["_studies"].astype(int),
        "arab": ["✓" if str(v).upper() in {"1", "Y", "TRUE", "YES"} else "" for v in
                 df.get("is_arab_related_flag", pd.Series([""] * len(df)))],
    })


def _render_results(df: pd.DataFrame, opts: dict) -> int | None:
    shown = df.head(opts["limit"])
    disease = resolve_disease(opts["query"]) if opts["mode"] == "disease" else None
    query_label = disease.display_name(is_rtl()) if disease else opts["query"]

    st.markdown(
        f"""<div class="result-summary">{html.escape(t('search.found'))}
        <strong>{len(df):,}</strong> {html.escape(t('search.results_for'))}
        <strong>«{html.escape(query_label)}»</strong>
        <span class="badge badge-neutral">{shown['rsid'].nunique()} SNP</span>
        <span class="badge badge-neutral">{shown['gene_symbol'].nunique()} {html.escape(t('search.genes_label'))}</span>
        </div>""",
        unsafe_allow_html=True,
    )
    if len(df) > len(shown):
        st.caption(t('search.showing_top').format(n=len(shown)))

    event = st.dataframe(
        _table(shown),
        hide_index=True,
        width="stretch",
        height=min(42 + 35 * len(shown), 460),
        on_select="rerun",
        selection_mode="single-row",
        key=f"{KEY}_table",
        column_config={
            "rsid": st.column_config.TextColumn("SNP"),
            "gene": st.column_config.TextColumn(t('search.col_gene')),
            "disease": st.column_config.TextColumn(t('search.col_disease'), width="medium"),
            "score": st.column_config.ProgressColumn(t('search.col_score'), min_value=0, max_value=100,
                                                     format="%.0f"),
            "rank": st.column_config.TextColumn(t('search.col_rank')),
            "p": st.column_config.TextColumn(t('search.col_p')),
            "studies": st.column_config.NumberColumn(t('search.col_studies'), format="%d"),
            "arab": st.column_config.TextColumn(t('search.col_arab'), width="small"),
        },
    )

    export = shown.drop(columns=[c for c in shown.columns if c.startswith("_")])
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        t('search.download'),
        data=export.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"snp_platform_{opts['mode']}_{stamp}.csv",
        mime="text/csv",
        icon="⬇️",
        key=f"{KEY}_download",
    )

    rows = event.selection.rows if event and event.selection else []
    return rows[0] if rows else None


def _render_no_results(result: dict, opts: dict, filtered_out: bool) -> None:
    if filtered_out:
        empty_state("🧹", t('search.none_filtered'), t('search.none_filtered_hint'))
    elif result.get("no_results_reason") == "arab_filter_empty":
        empty_state("🌍", t('search.none_arab'), t('search.none_arab_hint'))
    else:
        empty_state("🔍", t('search.none'), t(f'search.none_hint_{opts["mode"]}'))


# ---------------------------------------------------------------------------
# Details of the selected association
# ---------------------------------------------------------------------------

def _send_to(page: str, row: dict, results: pd.DataFrame) -> None:
    st.session_state["ai_selected_result_from_search"] = row
    st.session_state["study_selected_result_from_search"] = row
    st.session_state["last_search_results"] = results
    go_to_page(page)


def _render_details(row: pd.Series, results: pd.DataFrame) -> None:
    data = {k: v for k, v in row.items() if not str(k).startswith("_")}
    context = normalize_result_context(data)
    context["p_value"] = _format_p(row.get("p_value"))
    rsid, gene = _text(row.get("rsid")), _text(row.get("gene_symbol"))
    explanation = _text(row.get("score_explanation_arabic") if is_rtl() else row.get("score_explanation"), "")
    arab = str(row.get("is_arab_related_flag", "")).upper() in {"1", "Y", "TRUE", "YES"}

    section_title(t('search.details_title'))
    with st.container(border=True):
        arab_badge = f'<span class="badge badge-arab">{html.escape(t("search.arab_badge"))}</span>' if arab else ""
        st.markdown(
            f"""
            <div class="detail-head">
                <span class="detail-rsid">{html.escape(rsid)}</span>
                {rank_badge(row.get("rank_label"))}{arab_badge}
                <span class="detail-meta">{html.escape(t('search.col_gene'))}: <code>{html.escape(gene)}</code>
                · {html.escape(_disease_label(row))}</span>
            </div>
            <div class="fact-grid">
                {_fact(t('search.col_score'), _text(row.get('importance_score')))}
                {_fact(t('search.col_p'), _format_p(row.get('p_value')))}
                {_fact(t('search.risk_allele'), _text(row.get('risk_allele')))}
                {_fact(t('search.col_studies'), _text(row.get('study_count_for_disease_snp')))}
                {_fact(t('search.odds_ratio'), _text(row.get('odds_ratio')))}
                {_fact('PubMed', _text(row.get('pubmed_id')))}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if explanation:
            st.markdown(f"**{t('search.why_this_score')}** {explanation}")

        tabs = st.tabs([t('search.tab_reason'), t('search.tab_terms'), t('search.tab_ai'), t('search.tab_study')])
        prefix = f"{KEY}_{rsid}_{gene}"
        with tabs[0]:
            st.markdown(build_ranking_reason(context))
        with tabs[1]:
            render_glossary_terms(context)
        with tabs[2]:
            render_ai_explanation_for_result(context, prefix)
        with tabs[3]:
            render_study_summary_for_result(context, prefix)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button(t('search.open_study_page'), icon="📄", key=f"{prefix}_to_study", width="stretch"):
                _send_to("Study Summaries", data, results)
        with c2:
            if st.button(t('search.open_ai_page'), icon="🧠", key=f"{prefix}_to_ai", width="stretch"):
                _send_to("AI Explanation", data, results)
        with c3:
            pubmed = _text(row.get("pubmed_id"), "")
            if pubmed.isdigit():
                st.link_button(t('search.open_pubmed'), f"https://pubmed.ncbi.nlm.nih.gov/{pubmed}/",
                               icon="🔗", width="stretch")


def _fact(label: str, value: str) -> str:
    return (f'<div class="fact"><div class="fact-label">{html.escape(label)}</div>'
            f'<div class="fact-value">{html.escape(value)}</div></div>')


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def _remember(opts: dict, count: int) -> None:
    item = {"time": datetime.now().strftime("%H:%M"), "query": opts["query"], "mode": opts["mode"], "count": count}
    history = [h for h in st.session_state[f"{KEY}_history"] if h["query"] != item["query"]]
    st.session_state[f"{KEY}_history"] = [item, *history][:HISTORY_LIMIT]

    user = get_current_user()
    marker = f"{opts['mode']}|{opts['query']}|{count}"
    if user and st.session_state.get(f"{KEY}_last_saved") != marker:
        try:
            save_user_search_history(query=opts["query"], search_mode=opts["mode"], result_count=count)
            st.session_state[f"{KEY}_last_saved"] = marker
        except Exception:
            pass  # history must never break the search itself


def _render_history() -> None:
    user = get_current_user()
    with st.expander(t('search.history'), icon="🕘"):
        if user:
            saved = get_my_search_history(limit=30)
            if saved.empty:
                st.caption(t('search.history_empty'))
                return
            st.dataframe(saved[["search_mode", "query", "result_count", "created_at"]], hide_index=True,
                         width="stretch")
            if st.button(t('search.history_clear'), key=f"{KEY}_clear_history"):
                clear_my_search_history()
                st.rerun()
            return

        history = st.session_state.get(f"{KEY}_history", [])
        if not history:
            st.caption(t('search.history_empty'))
            return
        for index, item in enumerate(history):
            st.button(f"{item['time']} · {item['query']} ({item['count']})", key=f"{KEY}_hist_{index}",
                      on_click=_set_query, args=(item["query"],), type="tertiary")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_disease_search_page() -> None:
    _init_state()
    page_header(t('search.title'), subtitle=t('search.subtitle'), icon="🔎")

    opts = _render_search_panel()

    if not opts["query"]:
        empty_state("🧬", t('search.start_title'), t('search.start_text'))
        _render_history()
        return

    result = search_tri_ranked_file(query=opts["query"], search_mode=opts["mode"],
                                    arab_related_only=opts["arab_only"], limit=5000)
    raw = pd.DataFrame(result.get("results", []))
    filtered = _apply_filters(raw, opts) if not raw.empty else raw

    if filtered.empty:
        _render_no_results(result, opts, filtered_out=not raw.empty)
        _remember(opts, 0)
        _render_history()
        return

    _remember(opts, len(filtered))
    selected = _render_results(filtered, opts)
    shown = filtered.head(opts["limit"])
    if selected is None or selected >= len(shown):
        selected = 0
    _render_details(shown.iloc[selected], shown)
    _render_history()
