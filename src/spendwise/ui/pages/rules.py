from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from spendwise.db.models import Category, Rule, RuleType
from spendwise.db.session import session_scope


def render():
    st.header("🏷️ التصنيفات وقواعد التصنيف")
    family_member_id = st.session_state.get("active_family_member_id")

    tab_categories, tab_rules = st.tabs(["التصنيفات", "القواعد"])

    with tab_categories:
        _render_categories()

    with tab_rules:
        _render_rules(family_member_id)


def _render_categories():
    with session_scope() as session:
        mains = list(session.execute(select(Category).where(Category.parent_id.is_(None)).order_by(Category.name_ar)).scalars())
        for main in mains:
            with st.expander(f"📁 {main.name_ar}" + ("" if main.is_active else " (معطّل)")):
                children = list(session.execute(select(Category).where(Category.parent_id == main.id).order_by(Category.name_ar)).scalars())
                for child in children:
                    c1, c2 = st.columns([4, 1])
                    c1.write(("• " + child.name_ar) if child.is_active else f"~~{child.name_ar}~~ (معطّل)")
                    toggle_label = "تعطيل" if child.is_active else "تفعيل"
                    if c2.button(toggle_label, key=f"toggle_cat_{child.id}"):
                        with session_scope() as s2:
                            cat = s2.get(Category, child.id)
                            cat.is_active = not cat.is_active
                        st.rerun()

                new_sub = st.text_input("إضافة تصنيف فرعي جديد", key=f"new_sub_{main.id}")
                if st.button("إضافة", key=f"add_sub_{main.id}") and new_sub.strip():
                    with session_scope() as s2:
                        s2.add(Category(name_ar=new_sub.strip(), parent_id=main.id))
                    st.rerun()

        st.divider()
        new_main = st.text_input("إضافة تصنيف رئيسي جديد")
        if st.button("إضافة تصنيف رئيسي") and new_main.strip():
            with session_scope() as s2:
                s2.add(Category(name_ar=new_main.strip(), parent_id=None))
            st.rerun()


def _render_rules(family_member_id):
    with session_scope() as session:
        rules = list(
            session.execute(
                select(Rule).where((Rule.family_member_id.is_(None)) | (Rule.family_member_id == family_member_id)).order_by(Rule.priority)
            ).scalars()
        )

        categories = list(session.execute(select(Category).where(Category.is_active.is_(True))).scalars())
        # Skip parent categories that have active subcategories — they're
        # grouping headers, not real assignable categories, and duplicate
        # every child's label with the same prefix.
        parent_ids_with_children = {c.parent_id for c in categories if c.parent_id is not None}
        category_options = {
            c.id: (c.name_ar if c.parent_id is None else f"{c.parent.name_ar} / {c.name_ar}")
            for c in categories
            if not (c.parent_id is None and c.id in parent_ids_with_children)
        }

        st.caption("القواعد ذات الأولوية (الرقم) الأصغر تُجرَّب أولًا. القواعد بدون عضو محدد تنطبق على جميع الأعضاء.")

        for rule in rules:
            cols = st.columns([2, 2, 2, 1, 1, 1])
            cols[0].write(rule.pattern)
            cols[1].write(category_options.get(rule.category_id, "—"))
            cols[2].write(rule.rule_type.value)
            new_priority = cols[3].number_input("أولوية", value=rule.priority, key=f"prio_{rule.id}", label_visibility="collapsed")
            if new_priority != rule.priority:
                with session_scope() as s2:
                    s2.get(Rule, rule.id).priority = new_priority
                st.rerun()
            toggle_label = "تعطيل" if rule.is_active else "تفعيل"
            if cols[4].button(toggle_label, key=f"toggle_rule_{rule.id}"):
                with session_scope() as s2:
                    r = s2.get(Rule, rule.id)
                    r.is_active = not r.is_active
                st.rerun()
            if cols[5].button("حذف", key=f"delete_rule_{rule.id}"):
                with session_scope() as s2:
                    s2.delete(s2.get(Rule, rule.id))
                st.rerun()

        st.divider()
        st.subheader("إضافة قاعدة جديدة")
        pattern = st.text_input("النص/الكلمة المفتاحية (اسم التاجر المُنقّى)")
        rtype = st.selectbox("نوع القاعدة", [t.value for t in RuleType], format_func=lambda v: {
            "exact": "مطابقة تامة", "merchant_normalized": "اسم تاجر", "keyword": "كلمة مفتاحية", "learned": "متعلَّمة",
        }.get(v, v))
        cat_id = st.selectbox("التصنيف", list(category_options.keys()), format_func=lambda cid: category_options[cid])
        priority = st.number_input("الأولوية (الأصغر = أولى)", value=300)
        if st.button("إضافة القاعدة", type="primary") and pattern.strip():
            with session_scope() as s2:
                s2.add(
                    Rule(
                        rule_type=RuleType(rtype), pattern=pattern.strip(), category_id=cat_id,
                        priority=priority, is_active=True, family_member_id=family_member_id,
                    )
                )
            st.success("تمت إضافة القاعدة.")
            st.rerun()
