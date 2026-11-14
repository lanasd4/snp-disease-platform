"""
Knowledge library: reviewed papers, datasets, explanations and protocols.
"""

from __future__ import annotations

import html

import streamlit as st

from app.ui.components import badge, empty_state, notice, page_header, section_title
from app.ui.references import reference_link
from core import community as cm
from core.auth import get_current_user, safe_log_admin_action
from core.diseases import list_diseases
from core.i18n import is_rtl, tr

TYPE_LABELS = {
    "paper": ("📄", "ورقة علمية", "Paper"),
    "dataset": ("🗂️", "بيانات", "Dataset"),
    "explanation": ("💡", "شرح", "Explanation"),
    "protocol": ("🧪", "بروتوكول", "Protocol"),
}
STATUS_LABELS = {
    cm.LIBRARY_PENDING: ("mid", "بانتظار المراجعة", "Waiting for review"),
    cm.LIBRARY_PUBLISHED: ("good", "منشور", "Published"),
    cm.LIBRARY_REJECTED: ("bad", "مرفوض", "Rejected"),
}


def type_label(item_type: str) -> str:
    icon, ar, en = TYPE_LABELS.get(item_type, ("📎", item_type, item_type))
    return f"{icon} {tr(ar, en)}"


def disease_options() -> dict:
    """Display name -> stored English name ('' = any)."""
    options = {tr("كل الأمراض", "All diseases"): ""}
    for d in list_diseases():
        options[d.display_name(is_rtl())] = d.name_en
    return options


def disease_label(name_en: str) -> str:
    for d in list_diseases():
        if d.name_en == name_en:
            return d.display_name(is_rtl())
    return name_en


def render_item(item: dict, show_status: bool = False) -> None:
    with st.container(border=True):
        tags = [badge(type_label(item["item_type"]), "neutral")]
        if item.get("disease"):
            tags.append(badge(disease_label(item["disease"]), "arab"))
        if item.get("gene"):
            tags.append(badge(item["gene"], "low"))
        if show_status:
            tone, ar, en = STATUS_LABELS.get(item["status"], ("low", item["status"], item["status"]))
            tags.append(badge(tr(ar, en), tone))
        st.markdown(" ".join(tags), unsafe_allow_html=True)
        st.markdown(f"**{html.escape(item['title'])}**")
        st.write(item["description"])
        links = []
        if item.get("reference_id"):
            links.append(reference_link(item))
        if item.get("url"):
            url = html.escape(item["url"], quote=True)
            links.append(f"<a href='{url}' target='_blank' rel='noopener noreferrer nofollow'>"
                         f"{tr('فتح الرابط', 'Open link')} ↗</a>")
        if links:
            st.markdown(" &nbsp;·&nbsp; ".join(links), unsafe_allow_html=True)
        meta = f"{tr('أضافه', 'Added by')} {html.escape(item['submitted_by'])} · {item['created_at'][:10]}"
        st.markdown(f"<div class='post-meta'>{meta}</div>", unsafe_allow_html=True)
        if show_status and item["status"] == cm.LIBRARY_REJECTED and item.get("review_note"):
            st.caption(f"{tr('سبب الرفض', 'Reason')}: {item['review_note']}")


def render_browse() -> None:
    col_q, col_type, col_disease = st.columns([2, 1, 1])
    query = col_q.text_input(tr("بحث في المكتبة", "Search the library"), key="lib_query",
                             placeholder=tr("عنوان، جين، كلمة…", "Title, gene, keyword…"))
    types = {tr("كل الأنواع", "All types"): ""} | {type_label(k): k for k in TYPE_LABELS}
    item_type = types[col_type.selectbox(tr("النوع", "Type"), list(types), key="lib_type")]
    diseases = disease_options()
    disease = diseases[col_disease.selectbox(tr("المرض", "Disease"), list(diseases), key="lib_disease")]

    items = cm.list_library(item_type=item_type, disease=disease, query=query)
    if not items:
        empty_state("📚", tr("لا توجد مواد بعد", "Nothing here yet"),
                    tr("كن أول من يضيف مادة مفيدة للمكتبة.", "Be the first to add something useful."))
        return
    st.caption(tr(f"{len(items)} مادة", f"{len(items)} items"))
    for item in items:
        render_item(item)


def render_submit(user: dict | None) -> None:
    if not user:
        notice(tr("سجّل الدخول لتضيف مواد إلى المكتبة.", "Sign in to add material to the library."), "info")
        return
    notice(tr(
        "كل مادة تُراجع من الإدارة قبل نشرها. الأوراق العلمية تُضاف كرابط (رقم PubMed أو DOI) وليس كملف، "
        "احترامًا لحقوق النشر، ويُفحص المرجع آليًا: هل هو موجود، هل العنوان مطابق، وهل الورقة مسحوبة.",
        "Every item is reviewed by an admin before it is published. Papers are added as a link (PubMed ID or "
        "DOI), not as a file, to respect copyright. The reference is checked automatically: does it exist, "
        "does the title match, and has the paper been retracted.",
    ), "research")
    with st.form("library_submit", clear_on_submit=False):
        item_type = st.selectbox(tr("نوع المادة", "Material type"), list(TYPE_LABELS), format_func=type_label)
        title = st.text_input(tr("العنوان", "Title"), max_chars=cm.TITLE_MAX)
        description = st.text_area(tr("وصف مختصر: ما الذي تقدمه هذه المادة؟", "Short description: what does it offer?"),
                                   max_chars=cm.BODY_MAX)
        c1, c2 = st.columns(2)
        reference_id = c1.text_input(tr("رقم PubMed أو DOI", "PubMed ID or DOI"),
                                     placeholder="17463246 / 10.1038/nature05616")
        url = c2.text_input(tr("رابط (اختياري للأوراق)", "Link (optional for papers)"), placeholder="https://")
        c3, c4 = st.columns(2)
        diseases = disease_options()
        disease = diseases[c3.selectbox(tr("المرض المرتبط", "Related disease"), list(diseases))]
        gene = c4.text_input(tr("الجين (اختياري)", "Gene (optional)"), max_chars=20)
        rights = st.checkbox(tr("أؤكد أن المادة متاحة للنشر (رابط عام أو رخصة مفتوحة أو أملك حقها).",
                                "I confirm this material may be shared (public link, open licence, or I own it)."))
        submitted = st.form_submit_button(tr("إرسال للمراجعة", "Submit for review"), type="primary")
    if submitted:
        if not rights:
            st.error(tr("يرجى تأكيد حق النشر.", "Please confirm the sharing rights."))
            return
        try:
            with st.spinner(tr("نفحص المرجع…", "Checking the reference…")):
                item_id = cm.submit_library_item(user["username"], item_type, title, description, url=url,
                                                 reference_id=reference_id, disease=disease, gene=gene)
            safe_log_admin_action(user["username"], "library_submit",
                                  f"item {item_id}: type={item_type}, title={title[:80]}, reference={reference_id}")
        except cm.CommunityError as exc:
            st.error(str(exc))
            return
        st.success(tr("وصلنا طلبك، وسيظهر بعد موافقة الإدارة.", "Received. It will appear once an admin approves it."))

    mine = [i for s in (cm.LIBRARY_PENDING, cm.LIBRARY_PUBLISHED, cm.LIBRARY_REJECTED)
            for i in cm.list_library(status=s, submitted_by=user["username"])]
    if mine:
        section_title(tr("طلباتي", "My submissions"))
        for item in mine:
            render_item(item, show_status=True)


def render_library_page() -> None:
    page_header("Knowledge Library", "المكتبة المعرفية",
                "Papers, datasets, explanations and protocols shared by users and reviewed by the team.",
                "أوراق وبيانات وشروحات وبروتوكولات يشاركها المستخدمون وتراجعها الإدارة قبل النشر.", icon="📚")
    user = get_current_user()
    browse, submit = st.tabs([tr("تصفّح", "Browse"), tr("أضف مادة", "Add material")])
    with browse:
        render_browse()
    with submit:
        render_submit(user)
