"""
Ranking page: compare the ten diseases and inspect the top-ranked variants of one disease.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.components import empty_state, page_header, rank_text, section_title, stat_card
from core.diseases import list_diseases
from core.evidence import TIER_ORDER, sort_by_evidence
from core.i18n import is_rtl, t, tr
from core.search_engine import load_tri_search_data

KEY = "rank"
BRAND = ["#0A2158", "#0E7C8C", "#5B3291", "#1D4E9E", "#3FA7B5", "#8A6BBE", "#6C86B8", "#9AD0D7"]
RANK_ORDER = TIER_ORDER
RANK_COLORS = {"Confirmed": "#0A2158", "Strong": "#0E7C8C", "Suggestive": "#C98A12", "Below threshold": "#AAB4C5"}


def _per_variant(data: pd.DataFrame) -> pd.DataFrame:
    """One row per (disease, variant): its strongest evidence record, in evidence order."""
    data = data.copy()
    data["_p"] = pd.to_numeric(data["best_p_value"], errors="coerce")
    data["_arab"] = data["is_arab_related_flag"].astype(str).isin({"1", "Y", "True", "TRUE"})
    data["_replicated"] = pd.to_numeric(data["independent_gws_studies"], errors="coerce").fillna(0).astype(int)
    best = sort_by_evidence(data)
    variants = best.drop_duplicates(subset=["disease_name", "rsid"]).copy()
    arab_any = data.groupby(["disease_name", "rsid"])["_arab"].any()
    variants["_arab"] = [arab_any.get((d, r), False) for d, r in zip(variants["disease_name"], variants["rsid"])]
    return variants


def _disease_names() -> dict:
    arabic = is_rtl()
    return {d.name_en: d.display_name(arabic) for d in list_diseases()}


def _style(fig, height: int = 380):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), font=dict(family="IBM Plex Sans Arabic, Segoe UI"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), plot_bgcolor="white", paper_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#EEF1F6")
    fig.update_yaxes(gridcolor="#EEF1F6")
    return fig


def _render_comparison(variants: pd.DataFrame, data: pd.DataFrame) -> None:
    all_names = _disease_names()
    icons = {d.name_en: d.icon for d in list_diseases()}
    chosen = st.multiselect(
        tr("اختر الأمراض للمقارنة", "Choose diseases to compare"),
        list(all_names),
        default=list(all_names),
        format_func=lambda name: f"{icons.get(name, '')} {all_names[name]}",
        key=f"{KEY}_compare",
        placeholder=tr("اختر مرضين أو أكثر", "Pick two or more diseases"),
    )
    if len(chosen) < 2:
        empty_state("⚖️", tr("اختر مرضين على الأقل للمقارنة", "Pick at least two diseases to compare"))
        return
    names = {name: all_names[name] for name in chosen}
    variants = variants[variants["disease_name"].isin(chosen)]
    data = data[data["disease_name"].isin(chosen)]
    summary = (
        variants.groupby("disease_name")
        .agg(variants=("rsid", "nunique"), genes=("gene_symbol", "nunique"),
             confirmed=("evidence_tier", lambda s: int((s == 3).sum())), arab=("_arab", "sum"))
        .reindex(list(names)).fillna(0).reset_index()
    )
    summary["label"] = summary["disease_name"].map(names)
    summary["studies"] = summary["disease_name"].map(data.groupby("disease_name")["pubmed_id"].nunique()).fillna(0)
    share = summary["confirmed"] / summary["variants"].where(summary["variants"] > 0)
    summary["confirmed_share"] = share.fillna(0) * 100

    c1, c2 = st.columns(2)
    with c1:
        section_title(tr("عدد المتغيرات والجينات لكل مرض", "Variants and genes per disease"))
        long = summary.melt(id_vars="label", value_vars=["variants", "genes"], var_name="kind", value_name="n")
        long["kind"] = long["kind"].map({"variants": tr("متغيرات", "Variants"), "genes": tr("جينات", "Genes")})
        fig = px.bar(long, x="n", y="label", color="kind", barmode="group", orientation="h",
                     color_discrete_sequence=BRAND[:2], labels={"n": "", "label": "", "kind": ""},
                     category_orders={"label": list(names.values())})
        st.plotly_chart(_style(fig), width="stretch", key=f"{KEY}_counts")
    with c2:
        section_title(tr("مستويات الدليل لكل مرض", "Evidence levels per disease"))
        dist = variants.groupby(["disease_name", "rank_label"]).size().reset_index(name="n")
        dist["label"] = dist["disease_name"].map(names)
        dist["rank"] = dist["rank_label"].map(rank_text)
        fig = px.bar(dist, x="n", y="label", color="rank", orientation="h",
                     category_orders={"rank": [rank_text(r) for r in RANK_ORDER], "label": list(names.values())},
                     color_discrete_map={rank_text(r): c for r, c in RANK_COLORS.items()},
                     labels={"n": "", "label": "", "rank": ""})
        st.plotly_chart(_style(fig), width="stretch", key=f"{KEY}_dist")

    section_title(tr("ملخص المقارنة", "Comparison summary"),
                  tr("المتغيرات العربية = متغيرات لها دليل من عينة عربية أو شرق أوسطية",
                     "Arab variants = variants with evidence from an Arab / Middle East sample"))
    table = summary[["label", "variants", "genes", "studies", "confirmed_share", "arab"]].sort_values(
        "variants", ascending=False)
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "label": tr("المرض", "Disease"),
            "variants": st.column_config.NumberColumn(tr("المتغيرات", "Variants"), format="%d"),
            "genes": st.column_config.NumberColumn(tr("الجينات", "Genes"), format="%d"),
            "studies": st.column_config.NumberColumn(tr("الدراسات", "Studies"), format="%d"),
            "confirmed_share": st.column_config.ProgressColumn(
                tr("نسبة المؤكَّد", "Confirmed share"), min_value=0, max_value=100, format="%.0f%%",
                help=tr("نسبة المتغيرات التي تكرر ارتباطها في دراستين مستقلتين أو أكثر",
                        "Share of variants replicated in two or more independent studies")),
            "arab": st.column_config.NumberColumn(tr("متغيرات عربية", "Arab variants"), format="%d"),
        },
    )


def _render_disease(variants: pd.DataFrame) -> None:
    arabic = is_rtl()
    diseases = list_diseases()
    disease = st.selectbox(tr("اختر المرض", "Choose a disease"), diseases,
                           format_func=lambda d: f"{d.icon} {d.display_name(arabic)}", key=f"{KEY}_disease")
    rows = variants[variants["disease_name"] == disease.name_en]
    if rows.empty:
        empty_state("📊", tr("لا توجد بيانات", "No data"))
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card(tr("المتغيرات", "Variants"), rows["rsid"].nunique(), icon="🧬")
    with c2:
        stat_card(tr("الجينات", "Genes"), rows["gene_symbol"].nunique(), icon="🧪")
    with c3:
        stat_card(tr("مؤكَّدة", "Confirmed"), int((rows["evidence_tier"] == 3).sum()),
                  tr("تكررت في دراستين مستقلتين أو أكثر", "Replicated in 2+ independent studies"), icon="⭐")
    with c4:
        stat_card(tr("بدليل عربي", "Arab evidence"), int(rows["_arab"].sum()), icon="🌍")

    left, right = st.columns([1.6, 1])
    with left:
        section_title(tr("أعلى 20 متغيرًا", "Top 20 variants"))
        top = rows.head(20)
        st.dataframe(
            pd.DataFrame({
                "rsid": top["rsid"], "gene": top["gene_symbol"],
                "rank": top["rank_label"].map(rank_text),
                "studies": top["_replicated"],
                "p": top["_p"].map(lambda v: f"{v:.1e}" if pd.notna(v) else "—"),
            }),
            hide_index=True, width="stretch", height=740,
            column_config={
                "rsid": "SNP", "gene": tr("الجين", "Gene"),
                "rank": st.column_config.TextColumn(tr("مستوى الدليل", "Evidence"), help=t("search.tier_help")),
                "studies": st.column_config.NumberColumn(
                    tr("دراسات مستقلة", "Independent studies"), format="%d",
                    help=tr("عدد الدراسات المستقلة التي بلغ فيها الارتباط p < 5×10⁻⁸",
                            "Independent studies where the association reached p < 5×10⁻⁸")),
                "p": tr("أفضل قيمة p", "Best p-value"),
            },
        )
    with right:
        section_title(tr("الجينات الأكثر تكرارًا", "Most frequent genes"))
        genes = (rows.assign(gene=rows["gene_symbol"].str.split(r"\s*[-,;]\s*").str[0])
                 .groupby("gene").size().sort_values(ascending=False).head(12).reset_index(name="n"))
        fig = px.bar(genes.iloc[::-1], x="n", y="gene", orientation="h", color_discrete_sequence=[BRAND[1]],
                     labels={"n": tr("عدد المتغيرات", "Variants"), "gene": ""})
        st.plotly_chart(_style(fig, 360), width="stretch", key=f"{KEY}_genes")

        section_title(tr("التكرار في دراسات مستقلة", "Replication in independent studies"))
        counts = rows["_replicated"].clip(upper=10).value_counts().sort_index().reset_index()
        counts.columns = ["k", "n"]
        counts["k"] = counts["k"].map(lambda k: "10+" if k >= 10 else str(int(k)))
        fig = px.bar(counts, x="k", y="n", color_discrete_sequence=[BRAND[0]],
                     labels={"k": tr("عدد الدراسات المستقلة", "Independent studies"),
                             "n": tr("عدد المتغيرات", "Variants")})
        fig.update_xaxes(type="category")
        st.plotly_chart(_style(fig, 300), width="stretch", key=f"{KEY}_hist")


def _render_method() -> None:
    with st.expander(tr("كيف يُحدَّد مستوى الدليل؟", "How is the evidence level decided?"), icon="ℹ️"):
        st.dataframe(
            pd.DataFrame([
                {"level": rank_text("Confirmed"), "rule": tr(
                    "دلالة على مستوى الجينوم (p < 5×10⁻⁸) في دراستين مستقلتين أو أكثر",
                    "Genome-wide significant (p < 5×10⁻⁸) in two or more independent studies")},
                {"level": rank_text("Strong"), "rule": tr(
                    "دلالة على مستوى الجينوم في دراسة واحدة", "Genome-wide significant in one study")},
                {"level": rank_text("Suggestive"), "rule": "p < 10⁻⁵"},
            ]),
            hide_index=True, width="stretch",
            column_config={"level": tr("المستوى", "Level"), "rule": tr("الشرط", "Rule")},
        )
        st.markdown(tr(
            "تُعدّ الدراسات المستقلة على كامل كتالوج GWAS، لا على السجلات المعروضة فقط. "
            "الترتيب حسب أفضل قيمة p في الكتالوج (قوة الدليل)، ثم المستوى، ثم حجم التأثير (|log OR| أو |β|)، "
            "ثم حجم العينة. أما المستوى فيبيّن مدى موثوقية الارتباط (هل تكرر).\n\n"
            "العينات العربية لا تغيّر المستوى؛ تظهر كشارة منفصلة ويمكن تصفية النتائج بها. "
            "مستوى الدليل يصف قوة الارتباط في الأبحاث، وليس تقديرًا لخطر الإصابة.",
            "Independent studies are counted over the whole GWAS Catalog, not only the records shown. "
            "Order is by best p-value in the catalog (strength), then level, effect size (|log OR| or |β|) and "
            "sample size. The level shows how reliable the association is (was it replicated).\n\n"
            "Arab samples do not change the level; they appear as a separate badge and filter. "
            "The evidence level describes research evidence, not a disease-risk estimate.",
        ))


def render_association_ranking_page() -> None:
    page_header(
        tr("ترتيب الارتباطات", "Association ranking"),
        subtitle=tr("قارن الأمراض العشرة، واستعرض أقوى المتغيرات الجينية لكل مرض حسب قوة الدليل العلمي.",
                    "Compare the ten diseases and browse each disease's strongest variants by strength of evidence."),
        icon="📊",
    )
    data = load_tri_search_data()
    if data.empty:
        empty_state("📊", tr("لا توجد بيانات مرتبة", "No ranked data"))
        return

    variants = _per_variant(data)
    tab_compare, tab_disease = st.tabs([tr("مقارنة الأمراض", "Compare diseases"),
                                        tr("ترتيب مرض محدد", "One disease")])
    with tab_compare:
        _render_comparison(variants, data)
    with tab_disease:
        _render_disease(variants)
    _render_method()
