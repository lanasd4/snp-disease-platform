"""
Shared "choose an association" picker used by the AI explanation and study summary pages.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from app.ui.components import rank_text
from core.evidence import sort_by_evidence

from core.diseases import list_diseases
from core.i18n import is_rtl, tr
from core.search_engine import load_tri_search_data

MAX_CHOICES = 40


def _label(row: pd.Series) -> str:
    disease = row.get("disease_arabic_name") if is_rtl() else row.get("disease_name")
    return f"{row.get('rsid')} · {row.get('gene_symbol')} · {disease} · {rank_text(row.get('rank_label'))}"


def pick_association(key: str, from_search_key: str, allow_none: bool = False) -> Optional[dict]:
    """Return the association the page should work on."""
    from_search = st.session_state.get(from_search_key)
    if from_search:
        with st.container(border=True):
            disease = from_search.get("disease_arabic_name") if is_rtl() else from_search.get("disease_name")
            st.markdown(
                f"**{tr('النتيجة المختارة من البحث', 'Result selected in Search')}:** "
                f"`{from_search.get('rsid')}` · `{from_search.get('gene_symbol')}` · {disease}"
            )
            if st.button(tr("اختيار نتيجة أخرى", "Choose another result"), key=f"{key}_clear", type="tertiary"):
                st.session_state.pop(from_search_key, None)
                st.rerun()
        return from_search

    data = load_tri_search_data()
    if data.empty:
        return None

    arabic = is_rtl()
    choices = ([None] if allow_none else []) + list(list_diseases())
    c1, c2 = st.columns([1, 2])
    with c1:
        disease = st.selectbox(
            tr("المرض", "Disease"),
            choices,
            format_func=lambda d: tr("سؤال عام (بدون نتيجة محددة)", "General question (no result)") if d is None
            else f"{d.icon} {d.display_name(arabic)}",
            key=f"{key}_disease",
        )
    if disease is None:
        return None

    rows = sort_by_evidence(data[data["disease_name"] == disease.name_en])
    rows = rows.drop_duplicates(subset=["rsid"]).head(MAX_CHOICES).reset_index(drop=True)
    if rows.empty:
        return None
    with c2:
        index = st.selectbox(tr("الارتباط", "Association"), range(len(rows)),
                             format_func=lambda i: _label(rows.iloc[i]), key=f"{key}_row")
    return {k: v for k, v in rows.iloc[index].to_dict().items() if not str(k).startswith("_")}
