from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

import streamlit as st

from spendwise.analytics.budget import get_budget, list_budgets, set_budget
from spendwise.db.session import session_scope


def render():
    st.header("🎯 الميزانية الشهرية")
    family_member_id = st.session_state.get("active_family_member_id")
    if family_member_id is None:
        st.warning("يرجى اختيار عضو من الشريط الجانبي أولًا.")
        return

    current_month = dt.date.today().strftime("%Y-%m")
    month = st.text_input("الشهر (YYYY-MM)", value=current_month)

    with session_scope() as session:
        existing = get_budget(session, family_member_id, month)
        current_amount = float(existing.amount) if existing else 0.0

    st.caption("حدد ميزانية إجمالية واحدة لهذا الشهر (بدون تفصيل حسب التصنيف في هذا الإصدار).")
    amount_str = st.text_input("مبلغ الميزانية", value=f"{current_amount:.2f}")

    if st.button("حفظ الميزانية", type="primary"):
        try:
            amount = Decimal(amount_str)
            if amount < 0:
                raise InvalidOperation
        except InvalidOperation:
            st.error("يرجى إدخال مبلغ صحيح وغير سالب.")
        else:
            with session_scope() as session:
                set_budget(session, family_member_id, month, amount)
            st.success(f"تم حفظ ميزانية شهر {month} بمقدار {amount:.2f}.")
            st.rerun()

    st.divider()
    st.subheader("الميزانيات السابقة")
    with session_scope() as session:
        budgets = list_budgets(session, family_member_id)
        if budgets:
            st.dataframe(
                [{"الشهر": b.month, "المبلغ": float(b.amount)} for b in budgets],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("لا توجد ميزانيات محفوظة بعد.")
