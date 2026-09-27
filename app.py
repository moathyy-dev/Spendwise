"""
SpendWise — نقطة الدخول الرئيسية لتطبيق Streamlit.
"""
from __future__ import annotations

import hmac

import streamlit as st

from spendwise import settings_store
from spendwise.config import get_settings
from spendwise.db.init_db import ensure_ready
from spendwise.db.session import session_scope
from spendwise.profiles import get_or_create_family_member, list_family_members
from spendwise.ui.style import RTL_CSS

st.set_page_config(page_title="SpendWise — سبيندوايز", page_icon="💰", layout="wide")
st.markdown(RTL_CSS, unsafe_allow_html=True)


def _check_password() -> bool:
    """Simple app-level password gate. Only active when SPENDWISE_APP_PASSWORD
    is configured (normally only for a public deployment, e.g. Streamlit
    Community Cloud) — for ordinary local desktop use, no password is set
    and this is a silent no-op, exactly as before."""
    settings = get_settings()
    if not settings.app_password:
        return True

    if st.session_state.get("_password_correct", False):
        return True

    st.title("🔒 SpendWise")
    st.caption("هذا التطبيق محمي بكلمة مرور لأنه منشور على رابط يمكن الوصول إليه عبر الإنترنت.")
    entered = st.text_input("كلمة المرور", type="password", key="_password_input")
    if st.button("دخول", type="primary"):
        if hmac.compare_digest(entered, settings.app_password):
            st.session_state["_password_correct"] = True
            st.rerun()
        else:
            st.error("كلمة المرور غير صحيحة.")
    return False


if not _check_password():
    st.stop()


@st.cache_resource
def _init_db_once():
    ensure_ready()
    return True


_init_db_once()


def _show_intro():
    st.title("مرحبًا بك في SpendWise 👋")
    st.markdown(
        """
### قبل أن تبدأ

**الخصوصية أولًا:** جميع بياناتك تُحفظ محليًا على جهازك فقط داخل قاعدة بيانات SQLite، ولا يتم رفعها لأي خادم خارجي.

**الملفات المرفوعة مؤقتة:** أي ملف تقوم برفعه (Excel أو PDF) يُستخدم فقط لاستخراج البيانات، ثم يُحذف فورًا بعد المعالجة — لا يُحفظ الملف الأصلي أبدًا.

**ما يُحفظ فعليًا:** التاريخ، المبلغ، العملة، التصنيف، واسم تاجر مُنقّى من أي معلومات حساسة (بدون أرقام حسابات أو آيبان أو أرقام هوية أو أرقام جوال).

**الذكاء الاصطناعي اختياري:** إذا فعّلت التصنيف الذكي عبر الإنترنت، يتم إرسال اسم التاجر المُنقّى والمبلغ فقط (بدون أي بيانات شخصية)، ويمكنك تعطيل هذه الميزة كليًا من صفحة الإعدادات في أي وقت.

**أنت من يوافق دائمًا:** لا تُحفظ أي معاملة في قاعدة البيانات إلا بعد مراجعتك واعتمادك لها صراحة.
        """
    )
    if st.button("فهمت، ابدأ الاستخدام", type="primary"):
        settings_store.set_flag("intro_seen", True)
        st.rerun()


if not settings_store.get_flag("intro_seen", False):
    _show_intro()
    st.stop()

with session_scope() as session:
    members = list_family_members(session)
    member_names = [m.name for m in members]

st.sidebar.title("💰 SpendWise")

if not member_names:
    st.sidebar.info("لا يوجد أعضاء بعد — أنشئ عضوًا للبدء.")
    new_name = st.sidebar.text_input("اسم العضو (مثال: أنا، الوالد، الوالدة)")
    if st.sidebar.button("إنشاء عضو") and new_name.strip():
        with session_scope() as session:
            member = get_or_create_family_member(session, new_name.strip())
            st.session_state["active_family_member_id"] = member.id
            st.session_state["active_family_member_name"] = member.name
        st.rerun()
    st.info("يرجى إنشاء عضو من الشريط الجانبي للبدء.")
    st.stop()

if "active_family_member_name" not in st.session_state or st.session_state.get("active_family_member_name") not in member_names:
    st.session_state["active_family_member_name"] = member_names[0]

selected_name = st.sidebar.selectbox("العضو الحالي", member_names, index=member_names.index(st.session_state["active_family_member_name"]))
st.session_state["active_family_member_name"] = selected_name

with session_scope() as session:
    active_member = get_or_create_family_member(session, selected_name)
    st.session_state["active_family_member_id"] = active_member.id

with st.sidebar.expander("➕ إضافة عضو جديد"):
    new_name = st.text_input("اسم العضو الجديد", key="new_member_name")
    if st.button("إضافة", key="add_member_btn") and new_name.strip():
        with session_scope() as session:
            get_or_create_family_member(session, new_name.strip())
        st.rerun()

st.sidebar.divider()

PAGES = {
    "🏠 لوحة المعلومات": "home",
    "📥 استيراد بيانات جديدة": "import_wizard",
    "🏷️ التصنيفات والقواعد": "rules",
    "🎯 الميزانية الشهرية": "budget",
    "📊 التقارير والنسخ الاحتياطي": "reports",
    "⚙️ الإعدادات": "settings_page",
}

page_label = st.sidebar.radio("التنقل", list(PAGES.keys()))
page_module_name = PAGES[page_label]

import importlib

page_module = importlib.import_module(f"spendwise.ui.pages.{page_module_name}")
page_module.render()
