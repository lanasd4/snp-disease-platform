"""
Display helpers for automatic reference checks.
"""

from __future__ import annotations

import html

from app.ui.components import badge
from core.community import ref_details
from core.i18n import tr

_STATUS = {
    "verified": ("good", "✓ المرجع موجود ومطابق", "✓ Reference found and matches"),
    "title_mismatch": ("mid", "⚠ العنوان لا يطابق المرجع", "⚠ Title does not match the reference"),
    "retracted": ("bad", "✕ ورقة مسحوبة", "✕ Retracted paper"),
    "not_found": ("bad", "✕ المرجع غير موجود", "✕ Reference not found"),
    "invalid": ("bad", "✕ رقم مرجع غير صالح", "✕ Invalid reference ID"),
    "unreachable": ("neutral", "… تعذّر الفحص مؤقتًا", "… Could not check right now"),
}


def reference_badge(status: str | None) -> str:
    if not status:
        return ""
    tone, ar, en = _STATUS.get(status, ("neutral", status, status))
    return badge(tr(ar, en), tone)


def reference_link(row: dict) -> str:
    """HTML link to PubMed / DOI for a stored reference, with its check badge."""
    ref = (row.get("reference_id") or "").strip()
    if not ref:
        return ""
    details = ref_details(row)
    kind, value = details.get("kind"), details.get("identifier") or ref
    if kind == "pmid":
        url, label = f"https://pubmed.ncbi.nlm.nih.gov/{html.escape(value)}/", f"PMID {html.escape(value)}"
    elif kind == "doi":
        url, label = f"https://doi.org/{html.escape(value)}", f"DOI {html.escape(value)}"
    else:
        return f"<span>{html.escape(ref)}</span> {reference_badge(row.get('ref_status'))}"
    meta = " · ".join(html.escape(x) for x in (details.get("journal", ""), details.get("year", "")) if x)
    meta_html = f" <span class='muted'>({meta})</span>" if meta else ""
    return (f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{label}</a>{meta_html} "
            f"{reference_badge(row.get('ref_status'))}")
