from __future__ import annotations

import datetime as dt
import json
import os
import tempfile

import streamlit as st

from spendwise.analytics.budget import compute_budget_status
from spendwise.analytics.comparisons import compute_comparison
from spendwise.analytics.recommendations import generate_observations
from spendwise.config import get_settings
from spendwise.db.session import session_scope
from spendwise.export.backup import create_backup, restore_backup
from spendwise.export.excel_export import generate_excel_report
from spendwise.export.package import export_package, import_package, preview_package
from spendwise.export.pdf_export import generate_pdf_report
from spendwise.import_service import get_last_committed_batch, undo_last_import
from spendwise.profiles import list_accounts


def render():
    st.header("📊 التقارير والنسخ الاحتياطي")
    family_member_id = st.session_state.get("active_family_member_id")
    family_member_name = st.session_state.get("active_family_member_name", "")
    if family_member_id is None:
        st.warning("يرجى اختيار عضو من الشريط الجانبي أولًا.")
        return

    tab_report, tab_package, tab_backup, tab_undo = st.tabs(
        ["التقرير الشهري", "حزمة بيانات محمولة", "نسخة احتياطية كاملة", "التراجع عن استيراد"]
    )

    with tab_report:
        _render_monthly_report(family_member_id, family_member_name)
    with tab_package:
        _render_package(family_member_id, family_member_name)
    with tab_backup:
        _render_backup()
    with tab_undo:
        _render_undo(family_member_id)


def _render_monthly_report(family_member_id, family_member_name):
    month = st.text_input("الشهر (YYYY-MM)", value=dt.date.today().strftime("%Y-%m"), key="report_month")

    with session_scope() as session:
        comparison = compute_comparison(session, family_member_id, month)
        metrics = comparison.current
        if not metrics.has_sufficient_data:
            st.info(metrics.insufficient_data_reason_ar)
            return
        budget_status = compute_budget_status(session, family_member_id, month, metrics)
        observations = generate_observations(session, family_member_id, comparison, budget_status)

        col1, col2 = st.columns(2)
        if col1.button("📄 إنشاء تقرير PDF"):
            tmp_path = os.path.join(tempfile.gettempdir(), f"spendwise_report_{month}.pdf")
            generate_pdf_report(tmp_path, family_member_name, metrics, comparison, observations, budget_status)
            with open(tmp_path, "rb") as f:
                st.download_button("تنزيل تقرير PDF", f.read(), file_name=f"تقرير_{month}.pdf", mime="application/pdf")

        if col2.button("📊 إنشاء تقرير Excel"):
            tmp_path = os.path.join(tempfile.gettempdir(), f"spendwise_report_{month}.xlsx")
            generate_excel_report(tmp_path, family_member_name, metrics)
            with open(tmp_path, "rb") as f:
                st.download_button(
                    "تنزيل تقرير Excel", f.read(), file_name=f"تقرير_{month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


def _render_package(family_member_id, family_member_name):
    st.subheader("تصدير حزمة بيانات")
    st.caption("تحتوي فقط على المعاملات المعتمدة والتصنيفات والقواعد والميزانيات (بدون ملفات أو بيانات حساسة) — للنقل أو النسخ الاحتياطي فقط.")
    if st.button("تصدير الحزمة"):
        with session_scope() as session:
            package = export_package(session, family_member_id)
        data = json.dumps(package, ensure_ascii=False, indent=2)
        st.download_button("تنزيل ملف الحزمة", data, file_name=f"spendwise_package_{family_member_name}.json", mime="application/json")

    st.divider()
    st.subheader("استيراد حزمة بيانات")
    uploaded = st.file_uploader("اختر ملف حزمة (.json)", type=["json"], key="package_upload")
    if uploaded is not None:
        try:
            package = json.loads(uploaded.read())
        except json.JSONDecodeError:
            st.error("ملف الحزمة غير صالح.")
            return

        target_name = st.text_input("استيراد إلى عضو باسم:", value=package.get("family_member_name", ""))
        with session_scope() as session:
            from spendwise.profiles import get_or_create_family_member

            existing_member = None
            try:
                from sqlalchemy import select
                from spendwise.db.models import FamilyMember

                existing_member = session.execute(select(FamilyMember).where(FamilyMember.name == target_name)).scalar_one_or_none()
            except Exception:  # noqa: BLE001
                pass
            preview = preview_package(session, package, existing_member.id if existing_member else None)

        st.write(f"إجمالي المعاملات في الحزمة: {preview['total_transactions']}")
        st.write(f"معاملات جديدة سيتم استيرادها: {preview['new_count']}")
        st.write(f"معاملات مستوردة مسبقًا (سيتم تجاهلها): {preview['already_imported_count']}")

        if st.button("تأكيد الاستيراد/الدمج", type="primary") and target_name.strip():
            with session_scope() as session:
                result = import_package(session, package, target_name.strip())
            st.success(f"تم استيراد {result['imported_count']} معاملة جديدة (تم تجاهل {result['skipped_count']} مكررة).")


def _render_backup():
    st.subheader("نسخة احتياطية كاملة")
    settings = get_settings()
    db_path = settings.database_path
    from spendwise.settings_store import _OVERRIDE_PATH  # local JSON settings path

    if st.button("إنشاء نسخة احتياطية"):
        tmp_path = os.path.join(tempfile.gettempdir(), f"spendwise_backup_{dt.date.today().isoformat()}.zip")
        create_backup(tmp_path, db_path, str(_OVERRIDE_PATH))
        with open(tmp_path, "rb") as f:
            st.download_button("تنزيل النسخة الاحتياطية", f.read(), file_name=os.path.basename(tmp_path), mime="application/zip")

    st.divider()
    st.subheader("استعادة من نسخة احتياطية")
    st.warning("سيتم استبدال قاعدة البيانات الحالية بالكامل. سيتم أخذ نسخة أمان تلقائية من البيانات الحالية قبل الاستبدال.")
    confirm = st.checkbox("أفهم أن هذا سيستبدل بياناتي الحالية")
    uploaded = st.file_uploader("اختر ملف نسخة احتياطية (.zip)", type=["zip"], key="backup_upload")
    if uploaded is not None and confirm and st.button("استعادة الآن", type="primary"):
        tmp_path = os.path.join(tempfile.gettempdir(), "restore_upload.zip")
        with open(tmp_path, "wb") as f:
            f.write(uploaded.read())
        try:
            restore_backup(tmp_path, db_path, str(_OVERRIDE_PATH))
            st.success("تمت الاستعادة بنجاح. يرجى إعادة تشغيل التطبيق لتطبيق التغييرات.")
        except ValueError as exc:
            st.error(str(exc))


def _render_undo(family_member_id):
    st.subheader("التراجع عن آخر استيراد")
    with session_scope() as session:
        accounts = list_accounts(session, family_member_id)
        for account in accounts:
            batch = get_last_committed_batch(session, account.id)
            with st.container(border=True):
                st.write(f"**الحساب: {account.alias}**")
                if batch is None:
                    st.caption("لا يوجد استيراد سابق لهذا الحساب.")
                else:
                    st.write(f"آخر استيراد: {batch.label} — {batch.row_count} معاملة — بتاريخ {batch.committed_at}")
                    if st.button(f"التراجع عن هذا الاستيراد", key=f"undo_{account.id}"):
                        with session_scope() as s2:
                            undo_last_import(s2, account.id)
                        st.success("تم التراجع عن الاستيراد وحذف معاملاته.")
                        st.rerun()
