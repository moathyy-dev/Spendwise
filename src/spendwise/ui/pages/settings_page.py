from __future__ import annotations

import streamlit as st
from sqlalchemy import func, select

from spendwise import settings_store
from spendwise.config import get_settings
from spendwise.db.models import Category
from spendwise.db.session import session_scope


def render():
    st.header("⚙️ الإعدادات")
    settings = get_settings()

    st.subheader("التصنيف الذكي (AI) عبر الإنترنت")
    st.caption(
        "عند تفعيل هذه الميزة، يتم إرسال اسم تاجر مُنقّى من أي معلومات حساسة بالإضافة إلى المبلغ والاتجاه (مدين/دائن) فقط "
        "إلى مزوّد الذكاء الاصطناعي المحدد (Gemini حاليًا) لمساعدتك على تصنيف المعاملات غير الواضحة. "
        "لن يتم إرسال اسمك، رقم حسابك، أو أي بيانات تعريفية شخصية أبدًا."
    )

    # A single checkbox bound directly to the saved setting. (Previously this
    # gated a first-time "consent" checkbox behind a separate immediately-
    # persisted flag, while the checkbox itself only took effect after the
    # "حفظ الإعدادات" button below was clicked — those two different-timing
    # persistence paths could disagree mid-interaction and made the consent
    # block flash on/off. The consent notice is already shown as the caption
    # above on every load, so a separate gating step added confusion without
    # adding protection.)
    enable_ai = st.checkbox("تفعيل التصنيف الذكي عبر الإنترنت", value=settings.enable_online_ai)

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
    st.subheader("📂 إدارة التصنيفات")
    st.caption(
        "عدّل أسماء التصنيفات الحالية، عطّل/فعّل تصنيفًا (تعطيل تصنيف لا يحذف أي معاملات مرتبطة به، "
        "فقط يخفيه من قائمة الاختيار لاحقًا)، أو أضف تصنيفًا جديدًا — بدون الحاجة لتعديل الكود."
    )

    with session_scope() as session:
        categories = list(
            session.execute(select(Category).order_by(Category.sort_order, Category.id)).scalars()
        )

        if categories:
            header_cols = st.columns([3, 1, 1])
            header_cols[0].caption("الاسم")
            header_cols[1].caption("الحالة")
            header_cols[2].caption(" ")

        for cat in categories:
            cols = st.columns([3, 1, 1])
            new_name = cols[0].text_input(
                "الاسم", value=cat.name_ar, key=f"cat_name_{cat.id}", label_visibility="collapsed"
            )
            status_label = "نشط ✅" if cat.is_active else "معطّل ⛔"
            cols[1].write(status_label)

            name_changed = new_name.strip() and new_name.strip() != cat.name_ar
            action_col = cols[2]
            action_cols = action_col.columns(2)
            if name_changed and action_cols[0].button("💾", key=f"cat_save_{cat.id}", help="حفظ الاسم الجديد"):
                duplicate = session.execute(
                    select(Category).where(Category.name_ar == new_name.strip(), Category.id != cat.id)
                ).scalar_one_or_none()
                if duplicate:
                    st.warning(f"يوجد تصنيف آخر بنفس الاسم «{new_name.strip()}» مسبقًا.")
                else:
                    cat.name_ar = new_name.strip()
                    session.commit()
                    st.success("تم تحديث اسم التصنيف.")
                    st.rerun()

            toggle_icon = "⛔" if cat.is_active else "✅"
            toggle_help = "تعطيل هذا التصنيف" if cat.is_active else "إعادة تفعيل هذا التصنيف"
            if action_cols[1].button(toggle_icon, key=f"cat_toggle_{cat.id}", help=toggle_help):
                cat.is_active = not cat.is_active
                session.commit()
                st.rerun()

        st.markdown("**إضافة تصنيف جديد**")
        add_cols = st.columns([3, 1])
        new_cat_name = add_cols[0].text_input(
            "اسم التصنيف الجديد", key="new_cat_name", label_visibility="collapsed", placeholder="مثال: هدايا"
        )
        if add_cols[1].button("➕ إضافة", type="primary"):
            trimmed = new_cat_name.strip()
            if not trimmed:
                st.warning("اكتب اسم التصنيف أولًا.")
            else:
                exists = session.execute(
                    select(Category).where(Category.name_ar == trimmed)
                ).scalar_one_or_none()
                if exists:
                    st.warning("يوجد تصنيف بنفس الاسم مسبقًا.")
                else:
                    max_order = session.execute(
                        select(func.max(Category.sort_order)).where(Category.parent_id.is_(None))
                    ).scalar() or 0
                    session.add(
                        Category(
                            name_ar=trimmed,
                            parent_id=None,
                            is_active=True,
                            is_system=False,
                            sort_order=max_order + 1,
                        )
                    )
                    session.commit()
                    st.success(f"تمت إضافة تصنيف «{trimmed}».")
                    st.rerun()

    st.divider()
    st.caption("ملاحظة أمنية: مفاتيح الوصول (API Keys) تُقرأ فقط من ملف .env المحلي على جهازك، ولا يتم حفظها أو عرضها هنا أبدًا.")
