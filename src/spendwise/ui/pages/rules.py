from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from spendwise.categorize.rules_engine import normalize_merchant_for_matching
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


_RULE_TYPE_LABELS = {
    "exact": "مطابقة تامة", "merchant_normalized": "اسم تاجر", "keyword": "كلمة مفتاحية", "learned": "متعلَّمة",
}


def _member_filter(family_member_id):
    return Rule.family_member_id.is_(None) if family_member_id is None else Rule.family_member_id == family_member_id


def _find_duplicate_and_conflict(session, pattern: str, rtype: str, family_member_id, category_id, exclude_rule_id=None):
    """Compare against every OTHER rule with the same type + scope, normalized
    the same way the matching engine does (case/diacritic-insensitive) —
    otherwise "Jahez" and "jahez" would look different here but match
    identically at classification time, letting true duplicates slip in.
    Returns (exact_duplicate_rule_or_None, conflicting_rule_or_None)."""
    normalized_new = normalize_merchant_for_matching(pattern)
    same_scope_rules = list(
        session.execute(
            select(Rule).where(Rule.rule_type == RuleType(rtype), _member_filter(family_member_id))
        ).scalars()
    )
    if exclude_rule_id is not None:
        same_scope_rules = [r for r in same_scope_rules if r.id != exclude_rule_id]
    exact_duplicate = next(
        (r for r in same_scope_rules if normalize_merchant_for_matching(r.pattern) == normalized_new and r.category_id == category_id),
        None,
    )
    conflicting = next(
        (r for r in same_scope_rules if normalize_merchant_for_matching(r.pattern) == normalized_new and r.category_id != category_id),
        None,
    )
    return exact_duplicate, conflicting


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
        category_ids = list(category_options.keys())
        rtype_values = [t.value for t in RuleType]

        st.caption(
            "القواعد ذات الأولوية (الرقم) الأصغر تُجرَّب أولًا. القواعد بدون عضو محدد تنطبق على جميع الأعضاء. "
            "عدّل أي حقل ثم اضغط «💾 حفظ» — ما تحتاج تحذف القاعدة وتضيفها من جديد."
        )

        for rule in rules:
            with st.container(border=True):
                cols = st.columns([2, 2, 2, 1])
                new_pattern = cols[0].text_input(
                    "النص/الكلمة المفتاحية", value=rule.pattern, key=f"rule_pattern_{rule.id}", label_visibility="collapsed"
                )
                current_cat_index = category_ids.index(rule.category_id) if rule.category_id in category_ids else 0
                new_cat_id = cols[1].selectbox(
                    "التصنيف", category_ids, index=current_cat_index,
                    format_func=lambda cid: category_options[cid], key=f"rule_cat_{rule.id}", label_visibility="collapsed",
                )
                current_rtype_value = rule.rule_type.value if hasattr(rule.rule_type, "value") else rule.rule_type
                new_rtype = cols[2].selectbox(
                    "النوع", rtype_values, index=rtype_values.index(current_rtype_value),
                    format_func=lambda v: _RULE_TYPE_LABELS.get(v, v), key=f"rule_type_{rule.id}", label_visibility="collapsed",
                )
                new_priority = cols[3].number_input(
                    "أولوية", value=rule.priority, key=f"rule_prio_{rule.id}", label_visibility="collapsed"
                )

                trimmed_pattern = new_pattern.strip()
                changed = (
                    trimmed_pattern != rule.pattern
                    or new_cat_id != rule.category_id
                    or new_rtype != current_rtype_value
                    or new_priority != rule.priority
                )

                status_cols = st.columns([2, 1, 1, 2])
                status_cols[0].caption("نشطة ✅" if rule.is_active else "معطّلة ⛔")
                if status_cols[1].button(
                    "⛔" if rule.is_active else "✅", key=f"rule_toggle_{rule.id}",
                    help="تعطيل هذه القاعدة" if rule.is_active else "تفعيل هذه القاعدة",
                ):
                    with session_scope() as s2:
                        s2.get(Rule, rule.id).is_active = not rule.is_active
                    st.rerun()
                if status_cols[2].button("🗑️", key=f"rule_delete_{rule.id}", help="حذف هذه القاعدة"):
                    with session_scope() as s2:
                        s2.delete(s2.get(Rule, rule.id))
                    st.rerun()
                if changed and status_cols[3].button("💾 حفظ", key=f"rule_save_{rule.id}", type="primary"):
                    if not trimmed_pattern:
                        st.warning("النص/الكلمة المفتاحية لا يمكن أن تكون فارغة.")
                    else:
                        with session_scope() as s2:
                            exact_duplicate, conflicting = _find_duplicate_and_conflict(
                                s2, trimmed_pattern, new_rtype, family_member_id, new_cat_id, exclude_rule_id=rule.id
                            )
                            if exact_duplicate:
                                st.warning(
                                    f"توجد قاعدة أخرى مطابقة بنفس الحقول مسبقًا (#{exact_duplicate.id}) — "
                                    "التعديل غير مطلوب، هذي القاعدة مكررة."
                                )
                            else:
                                if conflicting:
                                    st.warning(
                                        f"تنبيه: يوجد قاعدة أخرى (#{conflicting.id}) بنفس النص لكن بتصنيف مختلف "
                                        f"({category_options.get(conflicting.category_id, '—')}). "
                                        "الأولوية الأصغر بينهما هي اللي بتُطبّق فعليًا. سيتم حفظ التعديل رغم ذلك."
                                    )
                                r = s2.get(Rule, rule.id)
                                r.pattern = trimmed_pattern
                                r.category_id = new_cat_id
                                r.rule_type = RuleType(new_rtype)
                                r.priority = new_priority
                                st.success("تم حفظ التعديلات.")
                                st.rerun()

        st.divider()
        st.subheader("إضافة قاعدة جديدة")
        pattern = st.text_input("النص/الكلمة المفتاحية (اسم التاجر المُنقّى)")
        rtype = st.selectbox("نوع القاعدة", rtype_values, format_func=lambda v: _RULE_TYPE_LABELS.get(v, v))
        cat_id = st.selectbox("التصنيف", category_ids, format_func=lambda cid: category_options[cid])
        priority = st.number_input("الأولوية (الأصغر = أولى)", value=300)
        if st.button("إضافة القاعدة", type="primary") and pattern.strip():
            trimmed_pattern = pattern.strip()
            with session_scope() as s2:
                exact_duplicate, conflicting = _find_duplicate_and_conflict(
                    s2, trimmed_pattern, rtype, family_member_id, cat_id
                )
                if exact_duplicate:
                    st.warning(
                        f"توجد قاعدة مطابقة بنفس الحقول مسبقًا (#{exact_duplicate.id}) — "
                        f"نفس النص والنوع والتصنيف والنطاق. ما احتجنا نضيفها مرة ثانية."
                    )
                else:
                    if conflicting:
                        st.warning(
                            f"تنبيه: يوجد قاعدة أخرى (#{conflicting.id}) بنفس النص «{trimmed_pattern}» "
                            f"لكن بتصنيف مختلف ({category_options.get(conflicting.category_id, '—')}). "
                            "الأولوية الأصغر بينهما هي اللي بتُطبّق فعليًا. سيتم إضافة القاعدة الجديدة رغم ذلك."
                        )
                    s2.add(
                        Rule(
                            rule_type=RuleType(rtype), pattern=trimmed_pattern, category_id=cat_id,
                            priority=priority, is_active=True, family_member_id=family_member_id,
                        )
                    )
                    st.success("تمت إضافة القاعدة.")
                    st.rerun()
