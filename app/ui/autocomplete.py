"""
Search box with live suggestions (a small in-project Streamlit component).

Suggestions are filtered in the browser as the user types; choosing one,
pressing Enter or clicking the search button returns the text at once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

_component = components.declare_component(
    "snp_autocomplete", path=str(Path(__file__).parent / "autocomplete_frontend"))


def autocomplete(options: list, key: str, default: str = "", placeholder: str = "", rtl: bool = False,
                 button_label: str = "Search") -> Optional[str]:
    """Return a newly submitted query, or None when nothing new was submitted."""
    event = _component(options=list(options), default=default or "", placeholder=placeholder, rtl=rtl,
                       button_label=button_label, max_items=8, key=key, default_value=None)
    seen_key = f"{key}__nonce"
    if isinstance(event, dict) and event.get("nonce") != st.session_state.get(seen_key):
        st.session_state[seen_key] = event.get("nonce")
        return str(event.get("query", "")).strip()
    return None
