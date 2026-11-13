"""
AI explanation page: plain-language explanation of an association or a
general genetics question.
"""

from __future__ import annotations

import streamlit as st

from app.ui.components import notice, page_header, section_title
from app.ui.pickers import pick_association
from core.ai.agent import generate_ai_explanation, get_ollama_models
from core.ai.model_manager import get_active_model
from core.auth import is_admin
from core.i18n import tr

KEY = "aiexp"
FROM_SEARCH_KEY = "ai_selected_result_from_search"


def render_ai_explanation_page() -> None:
    page_header(
        tr("الشرح الذكي", "AI explanation"),
        subtitle=tr("شرح مبسط لأي ارتباط جيني أو مفهوم في علم الوراثة، بلغة واضحة.",
                    "A plain-language explanation of any genetic association or genetics concept."),
        icon="🧠",
    )

    installed = get_ollama_models()
    active = get_active_model()
    model = active if active in installed else (installed[0] if installed else None)
    if is_admin():
        if model:
            notice(tr(f"يعمل الشرح بمساعد ذكي محلي ({model}).", f"Explanations use a local AI model ({model})."))
        else:
            notice(tr("يعمل الشرح بالقواعد العلمية المعتمدة داخل المنصة (لا يتوفر نموذج ذكاء اصطناعي محلي على هذا الخادم).",
                      "Explanations use the platform's built-in scientific rules (no local AI model on this server)."))

    section_title(tr("ماذا تريد أن تفهم؟", "What would you like to understand?"))
    row = pick_association(KEY, FROM_SEARCH_KEY, allow_none=True)

    question = st.text_area(
        tr("سؤالك (اختياري)", "Your question (optional)"),
        placeholder=tr("مثال: ماذا تعني قيمة p هنا؟ ما الفرق بين SNP والطفرة؟",
                       "e.g. What does the p-value mean here? How is a SNP different from a mutation?"),
        key=f"{KEY}_question",
    )

    if not st.button(tr("اشرح لي", "Explain"), type="primary", icon="✨", key=f"{KEY}_go"):
        return

    with st.spinner(tr("جاري إعداد الشرح...", "Preparing the explanation...")):
        result = generate_ai_explanation(row, user_question=question, prefer_ollama=bool(model), model_name=model)

    section_title(tr("الشرح", "Explanation"))
    if result.get("mode") == "scope_refusal":
        notice(tr("السؤال خارج نطاق المساعدة التعليمية في علم الوراثة.",
                  "This question is outside the platform's genetics-education scope."), "warn")
    with st.container(border=True):
        st.markdown(result.get("explanation", ""))
    notice(tr("هذا الشرح تعليمي فقط ولا يُستخدم للتشخيص أو القرارات العلاجية.",
              "This explanation is educational only and not for diagnosis or treatment decisions."), "research")

    if not is_admin():
        return
    with st.expander(tr("تفاصيل تقنية (للإدارة فقط)", "Technical details (admins only)")):
        st.write({"mode": result.get("mode"), "model": result.get("model"),
                  "fallback": result.get("used_fallback"), "safety_replaced": result.get("safety_replaced")})
