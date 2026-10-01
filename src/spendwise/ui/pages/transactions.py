from __future__ import annotations

import datetime as dt

import streamlit as st
from sqlalchemy import select

from spendwise.db.models import Account, Category, Transaction
from spendwise.db.session import session_scope
from spendwise.profiles import list_accounts

_TXN_TYPE_LABELS = {
    "expense": "مصروف",
    "income": "دخل",
    "transfer": "تحويل",
    "refund": "استرداد",
    "fee": "رسوم",
    "cash_withdrawal": "سحب نقدي",
    "unknown": "غير معروف",
}

_PAGE_SIZE = 50


def render():
    st.header("🧾 المعاملات")
    family_member_id = st.session_state.get("active_family_member_id")
    if family_member_id is None:
        st.warning("يرجى اختيار عضو من الشريط الجانبي أولًا.")
        return

    st.caption(
        "استعرض معاملاتك المحفوظة وعدّل تصنيف أي معاملة بعد اعتمادها — بدون الحاجة للتراجع عن الاستيراد كامل. "
        "عدّل التصنيف من القائمة المنسدلة ثم اضغط «💾» لكل معاملة."
    )

    current_month = dt.date.today().strftime("%Y-%m")

    with session_scope() as session:
        accounts = list_accounts(session, family_member_id, active_only=False)
        account_options = {0: "كل الحسابات"} | {a.id: a.alias for a in accounts}

        categories = list(session.execute(select(Category).where(Category.is_active.is_(True))).scalars())
        parent_ids_with_children = {c.parent_id for c in categories if c.parent_id is not None}
        category_options = {
            c.id: (c.name_ar if c.parent_id is None else f"{c.parent.name_ar} / {c.name_ar}")
            for c in categories
            if not (c.parent_id is None and c.id in parent_ids_with_children)
        }
        category_ids = list(category_options.keys())

    filter_cols = st.columns([2, 2, 3])
    month = filter_cols[0].text_input("الشهر (YYYY-MM)", value=current_month)
    account_id = filter_cols[1].selectbox(
        "الحساب", list(account_options.keys()), format_func=lambda aid: account_options[aid]
    )
    search = filter_cols[2].text_input("🔍 بحث باسم التاجر", placeholder="مثال: Jahez")

    if "txn_page" not in st.session_state:
        st.session_state["txn_page"] = 0

    try:
        year, mon = (int(p) for p in month.split("-"))
        month_start = dt.date(year, mon, 1)
        month_end = dt.date(year + 1, 1, 1) if mon == 12 else dt.date(year, mon + 1, 1)
