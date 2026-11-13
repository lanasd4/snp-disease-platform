
"""
Segmented Circos Plot Page
"""

from __future__ import annotations

from typing import Any
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.ui.components import empty_state, notice, page_header, stat_card
from core.diseases import list_diseases
from core.evidence import sort_by_evidence
from core.i18n import is_rtl, tr
from core.paths import PROJECT_ROOT


RANKED_PATH = PROJECT_ROOT / "data" / "processed" / "ranked_associations_initial.csv"


# -----------------------------
# Basic utilities
# -----------------------------

def _clean(value: Any, default: str = "") -> str:
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


def _to_float(value: Any, default: float = 0.0) -> float:
    text = _clean(value, "")

    if not text:
        return default

    try:
        return float(text)
    except Exception:
        return default


def _first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {str(c).lower(): c for c in df.columns}

    for candidate in candidates:
        c = candidate.lower()
        if c in lower_map:
            return lower_map[c]

    for candidate in candidates:
        c = candidate.lower()
        for existing_lower, original in lower_map.items():
            if c == existing_lower or c in existing_lower or existing_lower in c:
                return original

    return None


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = str(hex_color).strip().lstrip("#")

    if len(hex_color) != 6:
        return f"rgba(100,116,139,{alpha})"

    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    except Exception:
        return f"rgba(100,116,139,{alpha})"


# -----------------------------
# Load platform data
# -----------------------------

def load_ranked_relationships() -> pd.DataFrame:
    """Cached until the ranked file changes (e.g. after an admin merge)."""
    if not RANKED_PATH.exists():
        return pd.DataFrame()
    return _load_ranked_relationships(RANKED_PATH.stat().st_mtime_ns)


@st.cache_data(show_spinner=False, max_entries=2)
def _load_ranked_relationships(mtime_ns: int) -> pd.DataFrame:
    if not RANKED_PATH.exists():
        return pd.DataFrame()

    raw = pd.read_csv(RANKED_PATH)

    if raw.empty:
        return pd.DataFrame()

    disease_col = _first_col(raw, ["disease_name", "disease", "trait", "mapped_trait"])
    disease_ar_col = _first_col(raw, ["disease_arabic_name", "disease_arabic", "arabic_name"])
    gene_col = _first_col(raw, ["gene_symbol", "gene", "mapped_gene"])
    snp_col = _first_col(raw, ["rsid", "rs_id", "snp", "snp_id", "variant_id"])
    raw = sort_by_evidence(raw) if "evidence_tier" in raw.columns else raw
    p_col = _first_col(raw, ["p_value", "p-value", "pvalue"])
    rank_col = _first_col(raw, ["rank_label", "rank"])
    rank_ar_col = _first_col(raw, ["rank_label_arabic"])
    pubmed_col = _first_col(raw, ["pubmed_id", "pmid", "pubmed"])
    study_col = _first_col(raw, ["study_title", "study", "title"])

    if disease_col is None or gene_col is None or snp_col is None:
        return pd.DataFrame()

    df = pd.DataFrame()

    df["Disease"] = raw[disease_col].apply(lambda x: _clean(x, "Unknown disease"))
    df["Disease_AR"] = raw[disease_ar_col].apply(lambda x: _clean(x, "")) if disease_ar_col else ""
    df["Gene"] = raw[gene_col].apply(lambda x: _clean(x, "Unknown gene"))
    df["SNP"] = raw[snp_col].apply(lambda x: _clean(x, "Unknown SNP"))
    df["Evidence_Tier"] = pd.to_numeric(raw.get("evidence_tier", 0), errors="coerce").fillna(0).astype(int)
    df["Independent_Studies"] = pd.to_numeric(raw.get("independent_gws_studies", 0), errors="coerce").fillna(0).astype(int)
    df["P_value"] = raw[p_col].apply(lambda x: _clean(x, "")) if p_col else ""
    df["Rank_Label"] = raw[rank_col].apply(lambda x: _clean(x, "")) if rank_col else ""
    df["Rank_Label_AR"] = raw[rank_ar_col].apply(lambda x: _clean(x, "")) if rank_ar_col else ""
    df["PubMed_ID"] = raw[pubmed_col].apply(lambda x: _clean(x, "")) if pubmed_col else ""
    df["Study_Title"] = raw[study_col].apply(lambda x: _clean(x, "")) if study_col else ""

    df = df[
        (df["Disease"] != "Unknown disease") &
        (df["Gene"] != "Unknown gene") &
        (df["SNP"] != "Unknown SNP")
    ].copy()

    df = df.drop_duplicates(subset=["Disease", "Gene", "SNP"], keep="first").reset_index(drop=True)

    return df


# -----------------------------
# Geometry helpers
# -----------------------------

def _polar_point(angle_deg: float, radius: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return radius * math.cos(rad), radius * math.sin(rad)


def _arc_points(start_deg: float, end_deg: float, radius: float, steps: int = 60):
    angles = np.linspace(math.radians(start_deg), math.radians(end_deg), steps)
    return radius * np.cos(angles), radius * np.sin(angles)


def _bezier_curve(x0, y0, x1, y1, pull: float = 0.06, steps: int = 45):
    """Curve pulled toward the center to create chord-like links."""
    cx = (x0 + x1) * pull
    cy = (y0 + y1) * pull

    xs = []
    ys = []

    for i in range(steps):
        t = i / (steps - 1)
        x = ((1 - t) ** 2) * x0 + 2 * (1 - t) * t * cx + (t ** 2) * x1
        y = ((1 - t) ** 2) * y0 + 2 * (1 - t) * t * cy + (t ** 2) * y1
        xs.append(x)
        ys.append(y)

    return xs, ys


def _allocate_segments(
    labels: list[str],
    start_deg: float,
    end_deg: float,
    gap_deg: float,
) -> dict:
    """Allocate separate colored arc segments with gaps."""
    labels = list(labels)
    n = len(labels)

    if n == 0:
        return {}

    total_span = end_deg - start_deg
    usable_span = total_span - gap_deg * max(0, n - 1)
    segment_span = usable_span / n

    segments = {}
    current = start_deg

    for label in labels:
        seg_start = current
        seg_end = current + segment_span
        seg_mid = (seg_start + seg_end) / 2

        segments[label] = {
            "start": seg_start,
            "end": seg_end,
            "mid": seg_mid,
        }

        current = seg_end + gap_deg

    return segments


def _label_anchor(x: float) -> str:
    if x > 0.08:
        return "left"
    if x < -0.08:
        return "right"
    return "center"


# -----------------------------
# Plot construction
# -----------------------------

def build_segmented_circos_figure(
    df: pd.DataFrame,
    relationship_type: str = "All",
    max_diseases: int = 6,
    max_genes: int = 14,
    max_snps: int = 12,
    show_labels: bool = True,
) -> go.Figure:

    if df.empty:
        fig = go.Figure()
        fig.update_layout(height=760)
        return fig

    # Rows are already in evidence order: keep the first entities seen.
    diseases = (
        df["Disease"].drop_duplicates()
        .head(max_diseases)
        .tolist()
    )

    genes = (
        df["Gene"].drop_duplicates()
        .head(max_genes)
        .tolist()
    )

    snps = (
        df["SNP"].drop_duplicates()
        .head(max_snps)
        .tolist()
    )

    plot_df = df[
        df["Disease"].isin(diseases) &
        df["Gene"].isin(genes) &
        df["SNP"].isin(snps)
    ].copy()

    if plot_df.empty:
        fig = go.Figure()
        fig.update_layout(height=760)
        return fig

    # Sectors similar to the reference image:
    # Diseases on left, Genes on right, SNPs on bottom.
    disease_segments = _allocate_segments(diseases, 128, 230, gap_deg=3.0)
    gene_segments = _allocate_segments(genes, -42, 74, gap_deg=1.7)
    snp_segments = _allocate_segments(snps, 238, 322, gap_deg=2.0)

    disease_palette = [
        "#2563eb", "#06b6d4", "#22c55e", "#facc15",
        "#fb923c", "#ef4444", "#a855f7", "#14b8a6"
    ]

    disease_colors = {
        label: disease_palette[i % len(disease_palette)]
        for i, label in enumerate(diseases)
    }

    gene_color = "#0ea5a8"
    snp_color = "#8b5cf6"

    positions = {}
    fig = go.Figure()

    # Draw colored outer segments
    def add_segments(entity_type: str, segments: dict, colors: dict | str, width: int):
        for label, seg in segments.items():
            color = colors[label] if isinstance(colors, dict) else colors

            x_arc, y_arc = _arc_points(seg["start"], seg["end"], radius=1.03, steps=60)

            fig.add_trace(
                go.Scatter(
                    x=x_arc,
                    y=y_arc,
                    mode="lines",
                    line=dict(color=color, width=width),
                    hoverinfo="text",
                    text=f"{entity_type}: {label}",
                    showlegend=False,
                )
            )

            x0, y0 = _polar_point(seg["mid"], 0.985)
            lx, ly = _polar_point(seg["mid"], 1.22)

            positions[(entity_type, label)] = {
                "angle": seg["mid"],
                "x": x0,
                "y": y0,
                "label_x": lx,
                "label_y": ly,
                "color": color,
            }

    add_segments("Disease", disease_segments, disease_colors, width=18)
    add_segments("Gene", gene_segments, gene_color, width=15)
    add_segments("SNP", snp_segments, snp_color, width=14)

    # Inner guide circles
    for radius in [0.35, 0.68, 0.98]:
        theta = np.linspace(0, 2 * np.pi, 240)
        fig.add_trace(
            go.Scatter(
                x=radius * np.cos(theta),
                y=radius * np.sin(theta),
                mode="lines",
                line=dict(color="rgba(148,163,184,0.18)", width=1),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Draw curved links
    def add_link(
        source_key: tuple[str, str],
        target_key: tuple[str, str],
        color: str,
        width: float,
        hover_text: str,
        pull: float,
    ):
        if source_key not in positions or target_key not in positions:
            return

        p0 = positions[source_key]
        p1 = positions[target_key]

        xs, ys = _bezier_curve(
            p0["x"],
            p0["y"],
            p1["x"],
            p1["y"],
            pull=pull,
            steps=50,
        )

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="text",
                text=hover_text,
                showlegend=False,
            )
        )

    for _, row in plot_df.iterrows():
        disease = row["Disease"]
        gene = row["Gene"]
        snp = row["SNP"]
        tier = int(row["Evidence_Tier"])
        studies = int(row["Independent_Studies"])
        p_value = _clean(row.get("P_value", ""))
        rank_label = _clean(row.get("Rank_Label", ""))
        rank_ar = _clean(row.get("Rank_Label_AR", ""))

        link_width = 1.0 + 1.6 * tier + min(studies, 10) * 0.15

        disease_col = disease_colors.get(disease, "#2563eb")

        hover_common = (
            f"<b>{disease}</b><br>"
            f"Gene: {gene}<br>"
            f"SNP: {snp}<br>"
            f"{tr('دراسات مستقلة', 'Independent studies')}: {studies}<br>"
            f"p-value: {p_value}<br>"
            f"{tr('مستوى الدليل', 'Evidence')}: {rank_ar if is_rtl() else rank_label}"
        )

        if relationship_type in ["All", "Disease-Gene"]:
            add_link(
                ("Disease", disease),
                ("Gene", gene),
                _hex_to_rgba(disease_col, 0.30),
                link_width,
                "Disease ↔ Gene<br>" + hover_common,
                pull=0.035,
            )

        if relationship_type in ["All", "Gene-SNP"]:
            add_link(
                ("Gene", gene),
                ("SNP", snp),
                "rgba(139,92,246,0.28)",
                max(0.9, link_width * 0.72),
                "Gene ↔ SNP<br>" + hover_common,
                pull=0.075,
            )

        if relationship_type in ["All", "Disease-SNP"]:
            add_link(
                ("Disease", disease),
                ("SNP", snp),
                "rgba(14,165,168,0.20)",
                max(0.8, link_width * 0.55),
                "Disease ↔ SNP<br>" + hover_common,
                pull=0.055,
            )

    # Add labels only, no node circles
    if show_labels:
        def add_labels(entity_type: str, labels: list[str], font_color: str):
            for label in labels:
                key = (entity_type, label)
                if key not in positions:
                    continue

                p = positions[key]
                x = p["label_x"]
                y = p["label_y"]

                fig.add_annotation(
                    x=x,
                    y=y,
                    text=label,
                    showarrow=False,
                    font=dict(size=11, color=font_color),
                    xanchor=_label_anchor(x),
                    yanchor="middle",
                    align="center",
                )

        add_labels("Disease", diseases, "#0f2f66")
        add_labels("Gene", genes, "#0f2f66")
        add_labels("SNP", snps, "#0f2f66")

    # Sector titles
    fig.add_annotation(
        x=-1.24,
        y=0.77,
        text="<b>Diseases | الأمراض</b>",
        showarrow=False,
        font=dict(size=15, color="#2563eb"),
        xanchor="center",
    )

    fig.add_annotation(
        x=1.24,
        y=0.77,
        text="<b>Genes | الجينات</b>",
        showarrow=False,
        font=dict(size=15, color="#0ea5a8"),
        xanchor="center",
    )

    fig.add_annotation(
        x=0,
        y=-1.30,
        text="<b>SNPs | تعددات النوكليوتيد</b>",
        showarrow=False,
        font=dict(size=15, color="#8b5cf6"),
        xanchor="center",
    )

    # Legend traces
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="#2563eb", width=4),
        name="Disease ↔ Gene"
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="#8b5cf6", width=4),
        name="Gene ↔ SNP"
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="#0ea5a8", width=4),
        name="Disease ↔ SNP"
    ))

    fig.update_layout(
        height=830,
        margin=dict(l=20, r=20, t=30, b=20),
        plot_bgcolor="rgba(248,250,252,0)",
        paper_bgcolor="rgba(248,250,252,0)",
        xaxis=dict(visible=False, range=[-1.52, 1.52]),
        yaxis=dict(visible=False, range=[-1.42, 1.42]),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.05,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color="#0f2f66"),
        ),
        hovermode="closest",
    )

    fig.update_yaxes(scaleanchor="x", scaleratio=1)

    return fig


# -----------------------------
# Streamlit page
# -----------------------------

def render_circos_plot_page():
    page_header(
        tr("مخطط العلاقات (Circos)", "Relationship map (Circos)"),
        subtitle=tr("مخطط دائري يربط الأمراض بالجينات والمتغيرات الجينية؛ سماكة الرابط تعكس مستوى الدليل.",
                    "A circular map linking diseases, genes and variants; link width reflects the evidence level."),
        icon="🧬",
    )

    df = load_ranked_relationships()
    if df.empty:
        empty_state("🧬", tr("لا توجد بيانات للرسم", "No data to draw"))
        return

    arabic = is_rtl()
    names = {d.name_en: d.display_name(arabic) for d in list_diseases()}
    disease_options = ["__all__"] + sorted(df["Disease"].dropna().astype(str).unique().tolist())
    relation_labels = {
        "All": tr("كل العلاقات", "All relationships"),
        "Disease-Gene": tr("مرض ↔ جين", "Disease ↔ Gene"),
        "Gene-SNP": tr("جين ↔ متغير", "Gene ↔ SNP"),
        "Disease-SNP": tr("مرض ↔ متغير", "Disease ↔ SNP"),
    }

    c1, c2, c3, c4 = st.columns([1.6, 1, 1, 1])
    with c1:
        selected_disease = st.selectbox(
            tr("المرض", "Disease"), disease_options, key="segmented_circos_disease",
            format_func=lambda v: tr("كل الأمراض", "All diseases") if v == "__all__" else names.get(v, v))
    with c2:
        relationship_type = st.selectbox(tr("نوع العلاقة", "Relationship"), list(relation_labels),
                                         format_func=relation_labels.get, key="segmented_circos_relationship_type")
    with c3:
        min_tier = st.selectbox(
            tr("أدنى مستوى دليل", "Minimum evidence"), [0, 2, 3], key="segmented_circos_min_tier",
            format_func=lambda v: {0: tr("الكل", "All"), 2: tr("قوي فأعلى", "Strong or higher"),
                                   3: tr("مؤكَّد فقط", "Confirmed only")}[v])
    with c4:
        max_connections = st.slider(tr("أقصى عدد روابط", "Maximum links"), 10, 200, 60, step=10,
                                    key="segmented_circos_max_connections")

    with st.expander(tr("إعدادات العرض", "Display settings"), icon="⚙️"):
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            max_diseases = st.slider(tr("عدد الأمراض", "Diseases"), 3, 12, 10, key="segmented_circos_max_diseases")
        with s2:
            max_genes = st.slider(tr("عدد الجينات", "Genes"), 5, 30, 14, key="segmented_circos_max_genes")
        with s3:
            max_snps = st.slider(tr("عدد المتغيرات", "Variants"), 5, 30, 12, key="segmented_circos_max_snps")
        with s4:
            show_labels = st.toggle(tr("إظهار الأسماء", "Show labels"), value=True, key="segmented_circos_show_labels")

    filtered = df.copy()
    if selected_disease != "__all__":
        filtered = filtered[filtered["Disease"].astype(str).eq(selected_disease)].copy()
    filtered = filtered[filtered["Evidence_Tier"] >= int(min_tier)]
    filtered = filtered.head(max_connections).reset_index(drop=True)

    if filtered.empty:
        empty_state("🧹", tr("لا توجد علاقات مطابقة", "No matching relationships"),
                    tr("خفّف الفلاتر أعلاه.", "Relax the filters above."))
        return

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        stat_card(tr("الأمراض", "Diseases"), filtered["Disease"].nunique(), icon="🩺")
    with m2:
        stat_card(tr("الجينات", "Genes"), filtered["Gene"].nunique(), icon="🧪")
    with m3:
        stat_card(tr("المتغيرات", "Variants"), filtered["SNP"].nunique(), icon="🧬")
    with m4:
        stat_card(tr("الروابط", "Links"), len(filtered), icon="🔗")

    fig = build_segmented_circos_figure(
        filtered, relationship_type=relationship_type, max_diseases=max_diseases,
        max_genes=max_genes, max_snps=max_snps, show_labels=show_labels,
    )
    st.plotly_chart(fig, width="stretch", config={
        "displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

    notice(tr("أزرق: مرض ↔ جين · بنفسجي: جين ↔ متغير · فيروزي: مرض ↔ متغير. "
              "سماكة الرابط = مستوى الدليل وعدد الدراسات المستقلة.",
              "Blue: disease ↔ gene · Purple: gene ↔ variant · Teal: disease ↔ variant. "
              "Link width = evidence level and number of independent studies."))

    with st.expander(tr("بيانات العلاقات المستخدمة في المخطط", "Relationship data used in the map")):
        st.dataframe(filtered, width="stretch", hide_index=True)
        st.download_button(tr("تحميل (CSV)", "Download (CSV)"), data=filtered.to_csv(index=False).encode("utf-8-sig"),
                           file_name="circos_relationships.csv", mime="text/csv", icon="⬇️",
                           key="download_segmented_circos_relationships")

    with st.expander(tr("كيف تقرأ المخطط؟", "How to read the map"), icon="ℹ️"):
        st.markdown(tr(
            "- القطاعات تمثل الأمراض والجينات والمتغيرات الجينية.\n"
            "- الروابط الداخلية توضح العلاقة بين مرض وجين، أو جين ومتغير، أو مرض ومتغير.\n"
            "- عند ازدحام المخطط قلّل عدد العناصر من إعدادات العرض.",
            "- Segments are diseases, genes and genetic variants.\n"
            "- Inner links connect a disease and a gene, a gene and a variant, or a disease and a variant.\n"
            "- If the map is crowded, reduce the number of items in the display settings.",
        ))
