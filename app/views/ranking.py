"""
Ranking page: compare the ten diseases and inspect the top-ranked variants of one disease.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.components import empty_state, page_header, rank_text, section_title, stat_card
from core.diseases import list_diseases
from core.i18n import is_rtl, tr
from core.search_engine import load_tri_search_data

KEY = "rank"
BRAND = ["#0A2158", "#0E7C8C", "#5B3291", "#1D4E9E", "#3FA7B5", "#8A6BBE", "#6C86B8", "#9AD0D7"]
RANK_ORDER = ["Very High", "High", "Moderate", "Low"]
RANK_COLORS = {"Very High": "#0A2158", "High": "#0E7C8C", "Moderate": "#C98A12", "Low": "#AAB4C5"}

# (weight, Arabic, English) - same weights as pipeline/association_ranking.RANKING_WEIGHTS
SCORE_COMPONENTS = [
    (45, "قوة الدلالة الإحصائية (‎-log10 p، بحد أقصى 100)", "Statistical strength (-log10 p, capped at 100)"),
    (15, "عدد سجلات الدليل للمتغير والمرض", "Number of evidence records for the variant and disease"),
    (10, "عدد الدراسات المستقلة", "Number of independent studies"),
    (8, "عدد المجموعات السكانية", "Number of populations"),
    (5, "عدد مصادر البيانات", "Number of data sources"),
    (5, "توفر نسبة الأرجحية أو Beta", "Odds ratio / beta reported"),
    (5, "توفر الأليل المؤثر", "Risk allele reported"),
    (4, "توفر معرّف PubMed", "PubMed id available"),
    (3, "عينة عربية أو شرق أوسطية", "Arab / Middle East sample"),
]


def _per_variant(data: pd.DataFrame) -> pd.DataFrame:
    """One row per (disease, variant): its best-scored evidence record."""
    data = data.copy()
    data["_p"] = pd.to_numeric(data["p_value"], errors="coerce")
    data["_arab"] = data["is_arab_related_flag"].astype(str).isin({"1", "Y", "True", "TRUE"})
    best = data.sort_values(["importance_score_numeric", "_p"], ascending=[False, True])
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
        .agg(variants=("rsid", "nunique"), genes=("gene_symbol", "nunique"), median_score=("importance_score_numeric", "median"),
             arab=("_arab", "sum"))
        .reindex(list(names)).fillna(0).reset_index()
    )
    summary["label"] = summary["disease_name"].map(names)
    summary["studies"] = summary["disease_name"].map(data.groupby("disease_name")["pubmed_id"].nunique()).fillna(0)

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
        section_title(tr("توزيع قوة الارتباط", "Strength of association"))
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
    table = summary[["label", "variants", "genes", "studies", "median_score", "arab"]].sort_values("variants",
                                                                                                  ascending=False)
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "label": tr("المرض", "Disease"),
            "variants": st.column_config.NumberColumn(tr("المتغيرات", "Variants"), format="%d"),
            "genes": st.column_config.NumberColumn(tr("الجينات", "Genes"), format="%d"),
            "studies": st.column_config.NumberColumn(tr("الدراسات", "Studies"), format="%d"),
            "median_score": st.column_config.ProgressColumn(tr("وسيط الدرجة", "Median score"), min_value=0,
                                                            max_value=100, format="%.0f"),
            "arab": st.column_config.NumberColumn(tr("متغيرات عربية", "Arab variants"), format="%d"),
        },
    )


def _render_disease(variants: pd.DataFrame) -> None:
    arabic = is_rtl()
    diseases = list_diseases()
    disease = st.selectbox(tr("اختر المرض", "Choose a disease"), diseases,
                           format_func=lambda d: f"{d.icon} {d.display_name(arabic)}", key=f"{KEY}_disease")
    rows = variants[variants["disease_name"] == disease.name_en].sort_values("importance_score_numeric",
                                                                             ascending=False)
    if rows.empty:
        empty_state("📊", tr("لا توجد بيانات", "No data"))
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card(tr("المتغيرات", "Variants"), rows["rsid"].nunique(), icon="🧬")
    with c2:
        stat_card(tr("الجينات", "Genes"), rows["gene_symbol"].nunique(), icon="🧪")
    with c3:
        stat_card(tr("قوية جدًا", "Very high"), int((rows["rank_label"] == "Very High").sum()), icon="⭐")
    with c4:
        stat_card(tr("بدليل عربي", "Arab evidence"), int(rows["_arab"].sum()), icon="🌍")

    left, right = st.columns([1.6, 1])
    with left:
        section_title(tr("أعلى 20 متغيرًا", "Top 20 variants"))
        top = rows.head(20)
        st.dataframe(
            pd.DataFrame({
                "rsid": top["rsid"], "gene": top["gene_symbol"], "score": top["importance_score_numeric"],
                "rank": top["rank_label"].map(rank_text),
                "p": top["_p"].map(lambda v: f"{v:.1e}" if pd.notna(v) else "—"),
                "studies": pd.to_numeric(top["study_count_for_disease_snp"], errors="coerce").fillna(0).astype(int),
            }),
            hide_index=True, width="stretch", height=740,
            column_config={
                "rsid": "SNP", "gene": tr("الجين", "Gene"),
                "score": st.column_config.ProgressColumn(tr("الدرجة", "Score"), min_value=0, max_value=100,
                                                         format="%.0f"),
                "rank": tr("القوة", "Strength"), "p": tr("قيمة p", "p-value"),
                "studies": st.column_config.NumberColumn(tr("الدراسات", "Studies"), format="%d"),
            },
        )
    with right:
        section_title(tr("الجينات الأكثر تكرارًا", "Most frequent genes"))
        genes = (rows.assign(gene=rows["gene_symbol"].str.split(r"\s*[-,;]\s*").str[0])
                 .groupby("gene").size().sort_values(ascending=False).head(12).reset_index(name="n"))
        fig = px.bar(genes.iloc[::-1], x="n", y="gene", orientation="h", color_discrete_sequence=[BRAND[1]],
                     labels={"n": tr("عدد المتغيرات", "Variants"), "gene": ""})
        st.plotly_chart(_style(fig, 360), width="stretch", key=f"{KEY}_genes")

        section_title(tr("توزيع الدرجات", "Score distribution"))
        fig = px.histogram(rows, x="importance_score_numeric", nbins=20, color_discrete_sequence=[BRAND[0]],
                           labels={"importance_score_numeric": tr("درجة الأهمية", "Importance score")})
        fig.update_yaxes(title=tr("عدد المتغيرات", "Variants"))
        st.plotly_chart(_style(fig, 300), width="stretch", key=f"{KEY}_hist")


def _render_method() -> None:
    with st.expander(tr("كيف تُحسب درجة الأهمية؟", "How is the importance score computed?"), icon="ℹ️"):
        st.markdown(tr(
            "الدرجة من 0 إلى 100، وهي مجموع مكونات موزونة. كل مكوّن يُحوَّل أولًا إلى قيمة بين 0 و1 "
            "(الأعداد بمقياس لوغاريتمي حتى لا تطغى القيم الكبيرة):",
            "The score runs from 0 to 100 and is a weighted sum. Each component is first scaled to 0-1 "
            "(counts on a log scale so very large values do not dominate):",
        ))
        st.dataframe(
            pd.DataFrame([{"w": w, "c": tr(ar, en)} for w, ar, en in SCORE_COMPONENTS]),
            hide_index=True, width="stretch",
            column_config={"w": st.column_config.NumberColumn(tr("الوزن", "Weight"), format="%d"),
                           "c": tr("المكوّن", "Component")},
        )
        st.markdown(tr(
            "**التصنيف:** 85 فأكثر = قوي جدًا، 70-85 = قوي، 50-70 = متوسط، أقل من 50 = منخفض. "
            "الدرجة أداة لترتيب الأدلة داخل المنصة وليست تقديرًا لخطر الإصابة.",
            "**Labels:** 85+ very high, 70-85 high, 50-70 moderate, below 50 low. "
            "The score orders evidence within the platform; it is not a disease-risk estimate.",
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
