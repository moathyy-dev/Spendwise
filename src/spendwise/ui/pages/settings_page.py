from __future__ import annotations

import streamlit as st

from spendwise import settings_store
from spendwise.config import get_settings


def render():
    st.header("⚙️ الإعدادات")
    settings = get_settings()

    st.subheader("التصنيف الذكي (AI) عبر الإنترنت")
    st.caption(
        "عند تفعيل هذه الميزة، يتم إرسال اسم تاجر مُنقّى من أي معلومات حساسة بالإضافة إلى المبلغ والاتجاه (مدين/دائن) فقط "
        "إلى مزوّد الذكاء الاصطناعي المحدد (Gemini حاليًا) لمساعدتك على تصنيف المعاملات غير الواضحة. "
        "لن يتم إرسال اسمك، رقم حسابك، أو أي بيانات تعريفية شخصية أبدًا."
    )

    consent_given = settings_store.get_flag("ai_consent_given", False)
    current_enabled = settings.enable_online_ai

    if not consent_given and not current_enabled:
        agree = st.checkbox("أوافق على إرسال بيانات مُنقّاة (اسم تاجر + مبلغ فقط) إلى مزوّد الذكاء الاصطناعي عند الحاجة.")
        enable_ai = st.checkbox("تفعيل التصنيف الذكي عبر الإنترنت", value=False, disabled=not agree)
        if agree and enable_ai:
            settings_store.set_flag("ai_consent_given", True)
    else:
        enable_ai = st.checkbox("تفعيل التصنيف الذكي عبر الإنترنت", value=current_enabled)

    st.divider()
    st.subheader("حدود الثقة في التصنيف")
    st.caption("عند بلوغ التصنيف نسبة الثقة العليا يتم اعتماده تلقائيًا، وتحت النسبة الأدنى يتم تجربة الذكاء الاصطناعي (إن كان مفعّلًا).")
    auto_accept = st.slider("نسبة الاعتماد التلقائي للتصنيف المحلي (%)", 50, 100, settings.confidence_auto_accept)
    ai_fallback = st.slider("نسبة اللجوء للذكاء الاصطناعي عند التصنيف المحلي الضعيف (%)", 0, 100, settings.confidence_ai_fallback)

    st.divider()
    st.subheader("العملة")
    base_currency = st.text_input("العملة الأساسية", value=settings.base_currency, max_chars=3).upper()
    enable_online_fx = st.checkbox("جلب أسعار الصرف تلقائيًا من الإنترنت عند توفرها (اختياري)", value=settings.enable_online_fx)

    if st.button("حفظ الإعدادات", type="primary"):
        settings_store.save_overrides(
            {
                "enable_online_ai": bool(enable_ai),
                "confidence_auto_accept": auto_accept,
                "confidence_ai_fallback": ai_fallback,
                "base_currency": base_currency or "SAR",
                "enable_online_fx": bool(enable_online_fx),
            }
        )
        st.success("تم حفظ الإعدادات بنجاح.")
        st.rerun()

    st.divider()
    st.caption("ملاحظة أمنية: مفاتيح الوصول (API Keys) تُقرأ فقط من ملف .env المحلي على جهازك، ولا يتم حفظها أو عرضها هنا أبدًا.")
