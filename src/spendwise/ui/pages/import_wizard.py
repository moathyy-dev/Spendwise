from __future__ import annotations

import os
from decimal import Decimal

import streamlit as st

from spendwise.categorize.service import create_learned_rule
from spendwise.config import get_settings
from spendwise.db.models import Account, Category
from spendwise.db.session import session_scope
from spendwise.import_service import (
    DuplicateFileError,
    build_staged_rows,
    check_file_not_duplicate,
    commit_import,
    guess_mappings_for_extraction,
    run_categorization,
    run_cross_account_transfer_detection,
    run_duplicate_detection,
    run_refund_detection,
)
from spendwise.ingestion.excel_reader import read_excel
from spendwise.ingestion.pdf_reader import read_pdf
from spendwise.mapping.column_mapper import apply_manual_overrides
from spendwise.profiles import get_or_create_account, list_accounts
from spendwise.sanitize.fingerprint import fingerprint_file_bytes
from spendwise.sanitize.tempfiles import safe_temp_filename
from sqlalchemy import select


def render():
    family_member_id = st.session_state.get("active_family_member_id")
    if family_member_id is None:
        st.warning("يرجى اختيار عضو من الشريط الجانبي أولًا.")
        return

    st.header("📥 استيراد بيانات جديدة")

    step = st.session_state.get("iw_step", "upload")

    if step == "upload":
        _step_upload(family_member_id)
    elif step == "map_columns":
        _step_map_columns()
    elif step == "review":
        _step_review(family_member_id)
    elif step == "done":
        _step_done()


def _reset_wizard():
    for key in list(st.session_state.keys()):
        if key.startswith("iw_"):
            del st.session_state[key]
    st.session_state["iw_step"] = "upload"


def _step_upload(family_member_id: int):
    st.subheader("الخطوة ١: اختيار الحساب ورفع الملفات")

    with session_scope() as session:
        accounts = list_accounts(session, family_member_id)
        account_aliases = [a.alias for a in accounts]

    if account_aliases:
        chosen = st.selectbox("الحساب", account_aliases + ["+ إنشاء حساب جديد"])
    else:
        chosen = "+ إنشاء حساب جديد"
        st.info("لا يوجد حساب لهذا العضو بعد — أنشئ حسابًا جديدًا أدناه.")

    if chosen == "+ إنشاء حساب جديد":
        new_alias = st.text_input("اسم/رمز الحساب الجديد (مثال: الحساب الجاري، بطاقة الراجحي)")
    else:
        new_alias = None

    uploaded_files = st.file_uploader(
        "اختر ملف أو أكثر (Excel أو PDF)", type=["xlsx", "xls", "pdf"], accept_multiple_files=True
    )

    settings = get_settings()
    default_currency = settings.base_currency

    if st.button("متابعة", type="primary"):
        account_alias = new_alias.strip() if new_alias else chosen
        if not account_alias:
            st.error("يرجى تحديد اسم الحساب.")
            return
        if not uploaded_files:
            st.error("يرجى رفع ملف واحد على الأقل.")
            return

        with session_scope() as session:
            account = get_or_create_account(session, family_member_id, account_alias)
            account_id = account.id

        all_tables = []
        all_mappings = []
        file_fingerprints = []
        warnings = []

        for uploaded in uploaded_files:
            content = uploaded.read()
            file_fp = fingerprint_file_bytes(content)
            try:
                with session_scope() as session:
                    check_file_not_duplicate(session, account_id, file_fp)
            except DuplicateFileError as exc:
                st.error(f"«{uploaded.name}»: {exc}")
                continue

            tmp_name = safe_temp_filename(uploaded.name)
            tmp_path = os.path.join("/tmp", tmp_name)
            try:
                with open(tmp_path, "wb") as f:
                    f.write(content)

                ext = os.path.splitext(uploaded.name)[1].lower()
                if ext in (".xlsx", ".xls"):
                    extraction = read_excel(tmp_path)
                elif ext == ".pdf":
                    extraction = read_pdf(tmp_path)
                else:
                    st.error(f"«{uploaded.name}»: نوع ملف غير مدعوم.")
                    continue

                if extraction.is_empty:
                    st.warning(f"«{uploaded.name}»: لم يتم العثور على بيانات معاملات قابلة للقراءة.")
                    continue

                warnings.extend([f"«{uploaded.name}»: {w}" for w in extraction.warnings])
                mappings = guess_mappings_for_extraction(extraction)
                all_tables.append((uploaded.name, extraction))
                all_mappings.append(mappings)
                file_fingerprints.append(file_fp)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        if not all_tables:
            st.error("لم يتم استخراج أي بيانات صالحة من الملفات المرفوعة.")
            return

        st.session_state["iw_account_id"] = account_id
        st.session_state["iw_account_alias"] = account_alias
        st.session_state["iw_default_currency"] = default_currency
        st.session_state["iw_tables"] = all_tables
        st.session_state["iw_mappings"] = all_mappings
        st.session_state["iw_file_fingerprints"] = file_fingerprints
        st.session_state["iw_warnings"] = warnings
        st.session_state["iw_step"] = "map_columns"
        st.rerun()


def _step_map_columns():
    st.subheader("الخطوة ٢: مراجعة تطابق الأعمدة")

    for w in st.session_state.get("iw_warnings", []):
        st.warning(w)

    all_tables = st.session_state["iw_tables"]
    all_mappings = st.session_state["iw_mappings"]

    updated_mappings = []
    for (file_name, extraction), mappings in zip(all_tables, all_mappings):
        st.markdown(f"#### 📄 {file_name}")
        file_updated_mappings = []
        for t_idx, (table, mapping) in enumerate(zip(extraction.tables, mappings)):
            with st.expander(f"جدول: {table.source_description} ({len(table.rows)} صف)"):
                st.dataframe(table.rows[:5], use_container_width=True)
                overrides = {}
                for field in ["date", "description", "amount", "debit", "credit", "currency", "balance"]:
                    options = ["(بدون)"] + table.columns
                    current = mapping.mapping.get(field)
                    idx = options.index(current) if current in options else 0
                    choice = st.selectbox(
                        f"العمود المطابق لحقل: {field}", options, index=idx, key=f"map_{file_name}_{t_idx}_{field}"
                    )
                    overrides[field] = None if choice == "(بدون)" else choice
                new_mapping = apply_manual_overrides(mapping, overrides)
                if not new_mapping.is_minimally_viable():
                    st.error("يجب تحديد عمود للتاريخ وعمود للمبلغ (أو مدين/دائن) على الأقل.")
                file_updated_mappings.append(new_mapping)
        updated_mappings.append(file_updated_mappings)

    if st.button("متابعة إلى المعالجة والمراجعة", type="primary"):
        st.session_state["iw_mappings"] = updated_mappings
        _process_and_categorize()
        st.session_state["iw_step"] = "review"
        st.rerun()

    if st.button("رجوع"):
        _reset_wizard()
        st.rerun()


def _process_and_categorize():
    account_alias = st.session_state["iw_account_alias"]
    default_currency = st.session_state["iw_default_currency"]
    family_member_id = st.session_state["active_family_member_id"]
    all_tables = st.session_state["iw_tables"]
    all_mappings = st.session_state["iw_mappings"]

    staged_rows = []
    idx = 0
    for (file_name, extraction), mappings in zip(all_tables, all_mappings):
        rows = build_staged_rows(extraction, mappings, default_currency, account_alias, start_index=idx)
        staged_rows.extend(rows)
        idx += len(rows)

    settings = get_settings()

    from spendwise.ai_provider import build_ai_provider

    ai_provider = build_ai_provider(settings)

    account_id = st.session_state["iw_account_id"]

    with session_scope() as session:
        run_categorization(session, family_member_id, staged_rows, settings, ai_provider)
        run_cross_account_transfer_detection(session, family_member_id, staged_rows, account_id)

    run_duplicate_detection(staged_rows, account_alias)
    run_refund_detection(staged_rows, account_alias)

    st.session_state["iw_staged_rows"] = staged_rows


def _step_review(family_member_id: int):
    st.subheader("الخطوة ٣: مراجعة واعتماد المعاملات")
    staged_rows = st.session_state.get("iw_staged_rows", [])
    default_currency = st.session_state["iw_default_currency"]

    with session_scope() as session:
        categories = list(session.execute(select(Category).where(Category.is_active.is_(True))).scalars())
        # Parent categories that DO have active subcategories are pure grouping
        # headers, not something a transaction should ever be assigned to
        # directly — showing them as a separate option just duplicates every
        # child's label (e.g. "طعام وشراب" AND "طعام وشراب / مطاعم وكافيهات").
        # Only a parent with no children (a flat category) stays selectable.
        parent_ids_with_children = {c.parent_id for c in categories if c.parent_id is not None}
        category_options = {None: "غير مصنّف"}
        category_options.update(
            {
                c.id: (c.name_ar if c.parent_id is None else f"{c.parent.name_ar} / {c.name_ar}")
                for c in categories
                if not (c.parent_id is None and c.id in parent_ids_with_children)
            }
        )

    currencies_used = sorted({r.currency.upper() for r in staged_rows if r.txn_date is not None})
    fx_rates = {}
    non_base_currencies = [c for c in currencies_used if c != default_currency.upper()]
    if non_base_currencies:
        st.markdown("##### أسعار التحويل للعملات غير الأساسية")
        for cur in non_base_currencies:
            fx_rates[cur] = st.number_input(f"سعر تحويل {cur} إلى {default_currency}", min_value=0.0, value=1.0, key=f"fx_{cur}")

    approved_count = 0
    excluded_count = 0

    for row in staged_rows:
        if row.txn_date is None:
            st.error(f"صف #{row.row_index}: تعذّر التعرف على التاريخ — سيتم استبعاده تلقائيًا.")
            row.excluded = True
            continue

        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.write(f"**{row.merchant_sanitized}**")
            c2.write(row.txn_date.isoformat())
            direction_ar = "مدين (صرف)" if row.direction == "debit" else "دائن (إيداع)"
            c3.write(f"{row.amount:.2f} {row.currency} — {direction_ar}")

            if row.warnings:
                st.caption("⚠️ " + " ".join(row.warnings))

            options = list(category_options.keys())
            current_cat = row.manual_category_override if row.manual_category_override is not None else row.category_id
            idx = options.index(current_cat) if current_cat in options else 0
            chosen_cat = st.selectbox(
                "التصنيف", options, index=idx, format_func=lambda cid: category_options[cid], key=f"cat_{row.row_index}"
            )
            if chosen_cat != row.category_id:
                row.manual_category_override = chosen_cat

            st.caption(f"المصدر: {row.classification_source} — الثقة: {row.confidence}% — {row.explanation_ar}")

            if row.is_probable_duplicate:
                st.warning("⚠️ يُحتمل أن تكون هذه معاملة مكررة: " + " ".join(row.duplicate_reasons_ar))
            if row.is_transfer:
                st.info("🔁 يبدو أن هذه معاملة تحويل بين حساباتك — سيتم استثناؤها من إجمالي المصروفات/الدخل.")
            if row.is_refund:
                st.info("↩️ يبدو أن هذه معاملة استرداد لعملية سابقة.")

            decision = st.radio(
                "الإجراء", ["اعتماد", "استبعاد"], horizontal=True, key=f"decision_{row.row_index}"
            )
            row.excluded = decision == "استبعاد"

            if not row.excluded and chosen_cat != row.category_id and chosen_cat is not None:
                scope = st.radio(
                    "هل هذا التغيير لهذه المعاملة فقط أم يجب أن يصبح قاعدة مستقبلية؟",
                    ["هذه المعاملة فقط", "قاعدة مستقبلية لهذا التاجر"],
                    horizontal=True,
                    key=f"scope_{row.row_index}",
                )
                row._learn_scope = "future_rule" if scope == "قاعدة مستقبلية لهذا التاجر" else "single"
            else:
                row._learn_scope = "single"

            if row.excluded:
                excluded_count += 1
            else:
                approved_count += 1

    st.divider()
    st.subheader("ملخص المطابقة")
    kept_rows = [r for r in staged_rows if not r.excluded and r.txn_date is not None]
    income_total = sum(r.amount for r in kept_rows if r.direction == "credit")
    expense_total = sum(r.amount for r in kept_rows if r.direction == "debit")
    net = income_total - expense_total
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("معتمدة", approved_count)
    c2.metric("مستبعدة", excluded_count)
    c3.metric("إجمالي الدخل (دائن)", f"{income_total:.2f}")
    c4.metric("إجمالي المصروف (مدين)", f"{expense_total:.2f}")
    c5.metric("الصافي", f"{net:.2f}")

    col_a, col_b = st.columns(2)
    if col_a.button("✅ تأكيد وحفظ", type="primary"):
        _commit(family_member_id, staged_rows, fx_rates)
    if col_b.button("إلغاء والبدء من جديد"):
        _reset_wizard()
        st.rerun()


def _commit(family_member_id: int, staged_rows, fx_rates: dict):
    account_id = st.session_state["iw_account_id"]
    default_currency = st.session_state["iw_default_currency"]
    file_fingerprints = st.session_state["iw_file_fingerprints"]

    manual_fx_rates = {cur: Decimal(str(rate)) for cur, rate in fx_rates.items()}

    learn_requests = [
        (row.manual_category_override or row.category_id, row.merchant_sanitized, getattr(row, "_learn_scope", "single"))
        for row in staged_rows
        if not row.excluded and getattr(row, "_learn_scope", "single") == "future_rule" and (row.manual_category_override or row.category_id)
    ]

    try:
        with session_scope() as session:
            account = session.get(Account, account_id)
            commit_import(
                session=session,
                account=account,
                family_member_id=family_member_id,
                file_label=f"استيراد {len(file_fingerprints)} ملف/ملفات",
                file_fingerprints=file_fingerprints,
                approved_rows=staged_rows,
                base_currency=default_currency,
                manual_fx_rates=manual_fx_rates,
            )
            for category_id, merchant, scope in learn_requests:
                create_learned_rule(session, family_member_id, merchant, category_id, scope)
    except Exception as exc:  # noqa: BLE001
        st.error(f"حدث خطأ أثناء الحفظ ولم يتم حفظ أي بيانات: {exc}")
        return

    st.session_state["iw_step"] = "done"
    st.rerun()


def _step_done():
    st.success("✅ تم حفظ المعاملات المعتمدة بنجاح.")
    st.balloons()
    st.caption("يمكنك التراجع عن آخر استيراد من صفحة التقارير إذا احتجت لذلك.")
    col_a, col_b = st.columns(2)
    if col_a.button("استيراد ملف آخر"):
        _reset_wizard()
        st.rerun()
    if col_b.button("الانتقال إلى لوحة المعلومات"):
        _reset_wizard()
        st.session_state["_nav_override"] = "🏠 لوحة المعلومات"
        st.rerun()
