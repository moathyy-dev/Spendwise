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

    show_all_months = st.checkbox("عرض كل الشهور (بدلًا من شهر واحد فقط)", value=True)

    filter_cols = st.columns([2, 2, 3])
    month = filter_cols[0].text_input("الشهر (YYYY-MM)", value=current_month, disabled=show_all_months)
    account_id = filter_cols[1].selectbox(
        "الحساب", list(account_options.keys()), format_func=lambda aid: account_options[aid]
    )
    search = filter_cols[2].text_input("🔍 بحث باسم التاجر", placeholder="مثال: Jahez")

    if "txn_page" not in st.session_state:
        st.session_state["txn_page"] = 0

    month_start = month_end = None
    if not show_all_months:
        try:
            year, mon = (int(p) for p in month.split("-"))
            month_start = dt.date(year, mon, 1)
            if mon == 12:
                month_end = dt.date(year + 1, 1, 1)
            else:
                month_end = dt.date(year, mon + 1, 1)
        except (ValueError, IndexError):
            st.error("صيغة الشهر غير صحيحة — استخدم YYYY-MM.")
            return

    with session_scope() as session:
        query = (
            select(Transaction)
            .where(Transaction.family_member_id == family_member_id)
            .order_by(Transaction.txn_date.desc(), Transaction.id.desc())
        )
        if not show_all_months:
            query = query.where(Transaction.txn_date >= month_start, Transaction.txn_date < month_end)
        if account_id:
            query = query.where(Transaction.account_id == account_id)
        if search.strip():
            query = query.where(Transaction.merchant_sanitized.ilike(f"%{search.strip()}%"))

        all_txns = list(session.execute(query).scalars())

    total = len(all_txns)
    if total == 0:
        st.info("لا توجد معاملات مطابقة لهذا الشهر/الفلتر.")
        return

    max_page = max((total - 1) // _PAGE_SIZE, 0)
    st.session_state["txn_page"] = min(st.session_state["txn_page"], max_page)
    page = st.session_state["txn_page"]
    page_txns = all_txns[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]

    st.caption(f"{total} معاملة — صفحة {page + 1} من {max_page + 1}")

    header_cols = st.columns([1.3, 3, 1.3, 1, 2.5, 0.6])
    for col, label in zip(header_cols, ["التاريخ", "التاجر", "المبلغ", "النوع", "التصنيف", ""]):
        col.caption(label)

    for txn in page_txns:
        cols = st.columns([1.3, 3, 1.3, 1, 2.5, 0.6])
        cols[0].write(txn.txn_date.isoformat())
        cols[1].write(txn.merchant_sanitized or "—")
        sign = "-" if txn.direction.value == "debit" else "+"
        cols[2].write(f"{sign}{txn.amount:.2f}")
        cols[3].write(_TXN_TYPE_LABELS.get(txn.txn_type.value, txn.txn_type.value))

        options = [None] + category_ids
        current_index = options.index(txn.category_id) if txn.category_id in options else 0
        new_cat_id = cols[4].selectbox(
            "التصنيف",
            options,
            index=current_index,
            format_func=lambda cid: "— بدون تصنيف —" if cid is None else category_options[cid],
            key=f"txn_cat_{txn.id}",
            label_visibility="collapsed",
        )

        if cols[5].button("💾", key=f"txn_save_{txn.id}", help="حفظ التصنيف الجديد لهذه المعاملة"):
            with session_scope() as s2:
                t = s2.get(Transaction, txn.id)
                t.category_id = new_cat_id
                t.classification_source = t.classification_source.__class__.MANUAL
            st.success("تم حفظ التصنيف.")
            st.rerun()

    st.divider()
    nav_cols = st.columns([1, 1, 4])
    if nav_cols[0].button("⬅️ السابق", disabled=page <= 0):
        st.session_state["txn_page"] = page - 1
        st.rerun()
    if nav_cols[1].button("التالي ➡️", disabled=page >= max_page):
        st.session_state["txn_page"] = page + 1
        st.rerun()
