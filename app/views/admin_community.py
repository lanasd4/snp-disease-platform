"""
Admin review of library submissions and community reports.
"""

from __future__ import annotations

import streamlit as st

from app.ui.components import empty_state
from app.views.library import render_item
from core import community as cm
from core.auth import get_current_user, log_admin_action
from core.i18n import tr
from core.userdb import backend


def _admin() -> str:
    return (get_current_user() or {}).get("username", "admin")


def render_library_review() -> None:
    pending = cm.list_library(status=cm.LIBRARY_PENDING)
    if not pending:
        empty_state("✅", tr("لا توجد طلبات بانتظار المراجعة", "No submissions waiting for review"))
        return
    for item in pending:
        iid = int(item["id"])
        render_item(item, show_status=True)
        note = st.text_input(tr("ملاحظة (مطلوبة عند الرفض)", "Note (required when rejecting)"), key=f"lib_note_{iid}")
        c1, c2, c3 = st.columns(3)
        if c1.button(tr("✓ نشر", "✓ Publish"), key=f"lib_ok_{iid}", type="primary"):
            cm.review_library_item(iid, True, _admin(), note)
            log_admin_action(_admin(), "library_publish", f"item {iid}")
            st.rerun()
        if c2.button(tr("✕ رفض", "✕ Reject"), key=f"lib_no_{iid}"):
            try:
                cm.review_library_item(iid, False, _admin(), note)
                log_admin_action(_admin(), "library_reject", f"item {iid}: {note}")
                st.rerun()
            except cm.CommunityError as exc:
                st.error(str(exc))
        if item.get("reference_id") and c3.button(tr("↻ إعادة فحص المرجع", "↻ Re-check reference"),
                                                  key=f"lib_re_{iid}"):
            cm.recheck_library_reference(iid)
            st.rerun()
        st.divider()


def render_reports() -> None:
    reports = cm.list_reports()
    if not reports:
        empty_state("✅", tr("لا توجد بلاغات مفتوحة", "No open reports"))
        return
    kinds = {"post": tr("منشور", "Post"), "comment": tr("تعليق", "Comment"), "library": tr("مادة مكتبة", "Library item")}
    for r in reports:
        rid = int(r["id"])
        with st.container(border=True):
            st.markdown(f"**{kinds.get(r['target_type'], r['target_type'])} #{r['target_id']}** · "
                        f"{tr('من', 'by')} {r['reporter']} · {r['created_at'][:10]}")
            st.caption(f"{tr('النص', 'Content')}: {cm.get_target_text(r['target_type'], int(r['target_id']))[:300]}")
            st.write(f"{tr('السبب', 'Reason')}: {r['reason']}")
            c1, c2 = st.columns(2)
            if c1.button(tr("إخفاء المحتوى", "Hide content"), key=f"rep_hide_{rid}", type="primary"):
                cm.resolve_report(rid, _admin(), hide_content=True)
                log_admin_action(_admin(), "community_hide", f"{r['target_type']} {r['target_id']}")
                st.rerun()
            if c2.button(tr("تجاهل البلاغ", "Dismiss"), key=f"rep_keep_{rid}"):
                cm.resolve_report(rid, _admin(), hide_content=False)
                st.rerun()


def render_community_admin_tab() -> None:
    if backend() == "sqlite":
        st.caption(tr("التخزين: قاعدة بيانات محلية (SQLite).", "Storage: local SQLite database."))
    else:
        st.caption(tr("التخزين: PostgreSQL دائم.", "Storage: persistent PostgreSQL."))
    lib_tab, rep_tab = st.tabs([tr("طلبات المكتبة", "Library submissions"), tr("البلاغات", "Reports")])
    with lib_tab:
        render_library_review()
    with rep_tab:
        render_reports()
