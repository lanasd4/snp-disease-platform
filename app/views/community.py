"""
Community discussions. Everything here is labelled as users' opinion; votes show
user agreement only and never affect the platform's evidence level.
"""

from __future__ import annotations

import html

import streamlit as st

from app.ui.components import badge, empty_state, notice, page_header
from app.ui.references import reference_link
from app.views.library import disease_label, disease_options
from core import community as cm
from core.auth import get_current_user
from core.i18n import tr

OPINION_TAG = ("💬 رأي المستخدمين، ليس معلومة معتمدة", "💬 Users' opinion, not verified evidence")


def opinion_tag() -> str:
    return f"<span class='opinion-tag'>{tr(*OPINION_TAG)}</span>"


def _vote_buttons(user: dict | None, target_type: str, row: dict, key: str) -> None:
    up, down = st.columns([1, 1])
    mine = row.get("my_vote", 0)
    up_label = f"▲ {row['up']}"
    down_label = f"▼ {row['down']}"
    disabled = user is None
    if up.button(up_label, key=f"{key}_up", type="primary" if mine == 1 else "secondary", disabled=disabled,
                 help=tr("أوافق", "Agree")):
        cm.vote(user["username"], target_type, int(row["id"]), 1)
        st.rerun()
    if down.button(down_label, key=f"{key}_down", type="primary" if mine == -1 else "secondary", disabled=disabled,
                   help=tr("لا أوافق", "Disagree")):
        cm.vote(user["username"], target_type, int(row["id"]), -1)
        st.rerun()


def _report_box(user: dict | None, target_type: str, target_id: int, key: str) -> None:
    if not user:
        return
    with st.popover(tr("🚩 إبلاغ", "🚩 Report")):
        reason = st.text_input(tr("السبب", "Reason"), key=f"{key}_reason", max_chars=300)
        if st.button(tr("إرسال البلاغ", "Send report"), key=f"{key}_send"):
            try:
                cm.report(user["username"], target_type, target_id, reason)
                st.success(tr("شكرًا، ستراجعه الإدارة.", "Thanks, an admin will review it."))
            except cm.CommunityError as exc:
                st.error(str(exc))


def render_post(post: dict, user: dict | None) -> None:
    pid = int(post["id"])
    with st.container(border=True):
        tags = [opinion_tag()]
        if post.get("disease"):
            tags.append(badge(disease_label(post["disease"]), "arab"))
        if post.get("gene"):
            tags.append(badge(post["gene"], "low"))
        st.markdown(" ".join(tags), unsafe_allow_html=True)
        st.markdown(f"#### {html.escape(post['title'])}")
        st.write(post["body"])
        if post.get("reference_id"):
            st.markdown(f"{tr('المرجع', 'Reference')}: {reference_link(post)}", unsafe_allow_html=True)
        st.markdown(f"<div class='post-meta'>{html.escape(post['author'])} · {post['created_at'][:10]} · "
                    f"{tr('تعليقات', 'comments')}: {post['comments']}</div>", unsafe_allow_html=True)

        c_vote, c_report = st.columns([2, 1])
        with c_vote:
            _vote_buttons(user, "post", post, f"p{pid}")
        with c_report:
            _report_box(user, "post", pid, f"rp{pid}")

        with st.expander(tr(f"التعليقات ({post['comments']})", f"Comments ({post['comments']})")):
            for comment in cm.list_comments(pid, user["username"] if user else ""):
                cid = int(comment["id"])
                st.markdown(f"<div class='post-meta'>{html.escape(comment['author'])} · "
                            f"{comment['created_at'][:10]}</div>", unsafe_allow_html=True)
                st.write(comment["body"])
                c1, c2 = st.columns([2, 1])
                with c1:
                    _vote_buttons(user, "comment", comment, f"c{cid}")
                with c2:
                    _report_box(user, "comment", cid, f"rc{cid}")
                st.divider()
            if user:
                with st.form(f"comment_{pid}", clear_on_submit=True):
                    body = st.text_area(tr("أضف تعليقًا", "Add a comment"), max_chars=cm.COMMENT_MAX,
                                        key=f"cbody{pid}")
                    if st.form_submit_button(tr("تعليق", "Comment")):
                        try:
                            cm.add_comment(user["username"], pid, body)
                            st.rerun()
                        except cm.CommunityError as exc:
                            st.error(str(exc))
            else:
                st.caption(tr("سجّل الدخول لتعلّق أو تصوّت.", "Sign in to comment or vote."))


def render_new_post(user: dict | None) -> None:
    if not user:
        notice(tr("سجّل الدخول لتكتب منشورًا.", "Sign in to write a post."), "info")
        return
    with st.form("new_post", clear_on_submit=True):
        title = st.text_input(tr("العنوان", "Title"), max_chars=cm.TITLE_MAX)
        body = st.text_area(tr("النص", "Text"), max_chars=cm.BODY_MAX, height=160)
        c1, c2, c3 = st.columns(3)
        diseases = disease_options()
        disease = diseases[c1.selectbox(tr("المرض", "Disease"), list(diseases))]
        gene = c2.text_input(tr("الجين (اختياري)", "Gene (optional)"), max_chars=20)
        reference_id = c3.text_input(tr("مرجع: PubMed أو DOI (اختياري)", "Reference: PubMed or DOI (optional)"))
        agree = st.checkbox(tr("ألتزم بالقواعد: لا نصائح علاجية، ولا نتائج جينية شخصية، واحترام الآخرين.",
                               "I follow the rules: no medical advice, no personal genetic results, be respectful."))
        submitted = st.form_submit_button(tr("نشر", "Publish"), type="primary")
    if submitted:
        if not agree:
            st.error(tr("يرجى الموافقة على القواعد.", "Please accept the rules."))
            return
        try:
            with st.spinner(tr("نفحص المرجع…", "Checking the reference…")):
                cm.create_post(user["username"], title, body, disease=disease, gene=gene, reference_id=reference_id)
        except cm.CommunityError as exc:
            st.error(str(exc))
            return
        st.success(tr("تم النشر.", "Published."))


def render_community_page() -> None:
    page_header("Community", "المجتمع",
                "Discuss findings with other users. Posts are opinions, not platform evidence.",
                "ناقش النتائج مع المستخدمين الآخرين. المنشورات آراء وليست أدلة معتمدة من المنصة.", icon="💬")
    notice(tr(
        "التصويت هنا يعبّر عن رأي المستخدمين فقط، وهو منفصل تمامًا عن «مستوى الدليل» المبني على الأبحاث المنشورة. "
        "لا تُعتبر أي مشاركة نصيحة طبية.",
        "Votes here reflect user opinion only and are completely separate from the research-based evidence "
        "level. Nothing here is medical advice.",
    ), "warn")
    user = get_current_user()
    feed, write = st.tabs([tr("النقاشات", "Discussions"), tr("منشور جديد", "New post")])
    with feed:
        c1, c2 = st.columns([2, 1])
        diseases = disease_options()
        disease = diseases[c1.selectbox(tr("المرض", "Disease"), list(diseases), key="cm_disease")]
        sort = c2.radio(tr("الترتيب", "Sort"), ["new", "top"], horizontal=True, key="cm_sort",
                        format_func=lambda s: tr("الأحدث", "Newest") if s == "new" else tr("الأعلى تقييمًا", "Top"))
        posts = cm.list_posts(username=user["username"] if user else "", disease=disease, sort=sort)
        if not posts:
            empty_state("💬", tr("لا توجد نقاشات بعد", "No discussions yet"),
                        tr("ابدأ أول نقاش من تبويب «منشور جديد».", "Start the first one from the New post tab."))
        for post in posts:
            render_post(post, user)
    with write:
        render_new_post(user)
