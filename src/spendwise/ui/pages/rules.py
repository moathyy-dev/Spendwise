from __future__ import annotations

import io

import pandas as pd
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


_STATUS_LABEL_TO_BOOL = {"نشط": True, "معطّل": False}
_RULES_EXCEL_COLUMNS = ["المعرف", "النص/الكلمة المفتاحية", "التصنيف", "النوع", "الأولوية", "الحالة"]


def _build_rules_export_dataframe(rules, category_options) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "المعرف": r.id,
                "النص/الكلمة المفتاحية": r.pattern,
                "التصنيف": category_options.get(r.category_id, ""),
                "النوع": _RULE_TYPE_LABELS.get(r.rule_type.value if hasattr(r.rule_type, "value") else r.rule_type, ""),
                "الأولوية": r.priority,
                "الحالة": "نشط" if r.is_active else "معطّل",
            }
            for r in rules
        ],
        columns=_RULES_EXCEL_COLUMNS,
    )


def _parse_rules_import_dataframe(import_df: pd.DataFrame, category_options: dict, existing_ids: set):
    """Pure parsing/validation logic, kept separate from Streamlit calls so it
    can be unit-tested without a running app. Returns (updates, inserts,
    invalid_rows, ignored_ids):
      - updates: list of (rule_id, pattern, category_id, rtype, priority, is_active)
      - inserts: list of (pattern, category_id, rtype, priority, is_active)
      - invalid_rows: list of (excel_row_number, reason)
      - ignored_ids: list of (excel_row_number, rule_id) — an id in the file
        that no longer exists in the DB (e.g. deleted elsewhere); the row is
        skipped rather than silently re-inserted as a "new" rule, since that
        would reintroduce something the user deliberately removed.
    """
    category_name_to_id = {label: cid for cid, label in category_options.items()}
    rtype_label_to_value = {label: value for value, label in _RULE_TYPE_LABELS.items()}

    updates, inserts, invalid_rows, ignored_ids = [], [], [], []

    for row_num, row in enumerate(import_df.to_dict("records"), start=2):  # row 2 = first data row in Excel
        raw_id = str(row.get("المعرف") or "").strip()
        pattern = str(row.get("النص/الكلمة المفتاحية") or "").strip()
        cat_label = str(row.get("التصنيف") or "").strip()
        rtype_label = str(row.get("النوع") or "").strip()
        priority_raw = str(row.get("الأولوية") or "").strip()
        status_label = str(row.get("الحالة") or "").strip()

        if not pattern and not cat_label and not rtype_label and not priority_raw and not status_label:
            continue  # fully blank row (e.g. trailing empty row) — skip silently

        problems = []
        if not pattern:
            problems.append("النص/الكلمة المفتاحية فارغة")

        cat_id_resolved = category_name_to_id.get(cat_label)
        if cat_id_resolved is None:
            problems.append(f"تصنيف غير معروف: «{cat_label}»")

        rtype_resolved = rtype_label_to_value.get(rtype_label)
        if rtype_resolved is None:
            problems.append(f"نوع قاعدة غير معروف: «{rtype_label}»")

        priority_resolved = None
        try:
            priority_resolved = int(float(priority_raw))
        except (ValueError, TypeError):
            problems.append(f"أولوية غير صالحة: «{priority_raw}»")

        is_active_resolved = _STATUS_LABEL_TO_BOOL.get(status_label)
        if is_active_resolved is None:
            problems.append(f"حالة غير معروفة: «{status_label}» (يجب أن تكون «نشط» أو «معطّل»)")

        if problems:
            invalid_rows.append((row_num, "، ".join(problems)))
            continue

        if raw_id:
            try:
                rule_id = int(float(raw_id))
            except ValueError:
                invalid_rows.append((row_num, f"معرف غير صالح: «{raw_id}»"))
                continue
            if rule_id not in existing_ids:
                ignored_ids.append((row_num, rule_id))
                continue
            updates.append((rule_id, pattern, cat_id_resolved, rtype_resolved, priority_resolved, is_active_resolved))
        else:
            inserts.append((pattern, cat_id_resolved, rtype_resolved, priority_resolved, is_active_resolved))

    return updates, inserts, invalid_rows, ignored_ids


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
            "عدّل أي حقل ثم اضغط «💾» — ما تحتاج تحذف القاعدة وتضيفها من جديد. 🟢/🔴 يبيّن حالتها وتضغط عليه للتبديل."
        )

        header_cols = st.columns([3, 2, 2, 1, 0.6, 0.6, 0.6])
        for col, label in zip(header_cols, ["النص/الكلمة المفتاحية", "التصنيف", "النوع", "الأولوية", "الحالة", "", ""]):
            col.caption(label)

        for rule in rules:
            cols = st.columns([3, 2, 2, 1, 0.6, 0.6, 0.6])
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

            # A single toggle button doubles as the status indicator: 🟢
            # means active (click to disable), 🔴 means disabled (click to
            # enable) — no separate status column needed, keeping the whole
            # row on one line.
            if cols[4].button(
                "🟢" if rule.is_active else "🔴", key=f"rule_toggle_{rule.id}",
                help="القاعدة نشطة — اضغط للتعطيل" if rule.is_active else "القاعدة معطّلة — اضغط للتفعيل",
            ):
                with session_scope() as s2:
                    s2.get(Rule, rule.id).is_active = not rule.is_active
                st.rerun()
            if cols[5].button("🗑️", key=f"rule_delete_{rule.id}", help="حذف هذه القاعدة"):
                with session_scope() as s2:
                    s2.delete(s2.get(Rule, rule.id))
                st.rerun()
            # Always visible and always clickable — no "did anything change"
            # detection to get wrong. Clicking it re-saves whatever is
            # currently in the fields above, which is a harmless no-op if
            # nothing was actually edited.
            if cols[6].button("💾", key=f"rule_save_{rule.id}", help="حفظ التعديلات على هذه القاعدة", type="primary"):
                trimmed_pattern = new_pattern.strip()
                if not trimmed_pattern:
                    st.warning("النص/الكلمة المفتاحية لا يمكن أن تكون فارغة.")
                else:
                    saved = False
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
                            saved = True
                    # st.rerun() raises its own internal exception to stop the
                    # script immediately — calling it INSIDE the
                    # "with session_scope()" block above made session_scope's
                    # except-clause treat that as a failure and roll back the
                    # just-made edit instead of committing it, even though
                    # st.success() below had already made it look saved. It
                    # must run only after the "with" block has exited (so the
                    # commit has already happened).
                    if saved:
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
            added = False
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
                    added = True
            # Same reason as the edit-save button above: st.rerun() must run
            # after the "with" block has exited, never inside it.
            if added:
                st.success("تمت إضافة القاعدة.")
                st.rerun()

        st.divider()
        st.subheader("📊 تصدير / استيراد القواعد عبر إكسل")
        st.caption(
            "صدّر كل قواعدك الحالية كملف إكسل وعدّل عليه بحرية: غيّر أي عمود في صف موجود (يبقى عمود «المعرف» كما هو) "
            "لتحديث نفس القاعدة، احذف صفًا كاملًا لحذف تلك القاعدة لاحقًا من الواجهة، أو أضف صفًا جديدًا في الأسفل "
            "واترك عمود «المعرف» فارغًا لإضافة قاعدة جديدة. ثم ارفع الملف — التحديث يتم حسب «المعرف»، فلا يحصل تكرار."
        )

        export_df = _build_rules_export_dataframe(rules, category_options)
        excel_buffer = io.BytesIO()
        export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        st.download_button(
            "⬇️ تصدير القواعد كملف إكسل",
            data=excel_buffer.getvalue(),
            file_name="قواعد_التصنيف.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        uploaded_rules_file = st.file_uploader("📤 رفع ملف إكسل بعد التعديل", type=["xlsx"], key="rules_excel_upload")
        if uploaded_rules_file is not None:
            try:
                import_df = pd.read_excel(uploaded_rules_file, engine="openpyxl", dtype=str)
            except Exception as exc:  # noqa: BLE001
                st.error(f"تعذّرت قراءة الملف: {exc}")
                import_df = None

            if import_df is not None and not set(_RULES_EXCEL_COLUMNS).issubset(set(import_df.columns)):
                st.error("الملف لا يحتوي على الأعمدة المطلوبة — تأكد إنك ما غيّرت أسماء الأعمدة في الصف الأول.")
                import_df = None

            if import_df is not None:
                existing_ids = {r.id for r in rules}
                updates, inserts, invalid_rows, ignored_ids = _parse_rules_import_dataframe(
                    import_df, category_options, existing_ids
                )

                st.markdown("##### معاينة قبل التطبيق")
                summary_cols = st.columns(4)
                summary_cols[0].metric("تحديثات", len(updates))
                summary_cols[1].metric("قواعد جديدة", len(inserts))
                summary_cols[2].metric("صفوف غير صالحة", len(invalid_rows))
                summary_cols[3].metric("معرفات غير موجودة", len(ignored_ids))

                for row_num, reason in invalid_rows:
                    st.warning(f"صف {row_num}: {reason} — تم تجاهله.")
                for row_num, rid in ignored_ids:
                    st.warning(f"صف {row_num}: القاعدة #{rid} غير موجودة (ربما انحذفت) — تم تجاهل الصف بدل ما يضيفها كقاعدة جديدة.")

                if (updates or inserts) and st.button("✅ تأكيد تطبيق ملف الإكسل", type="primary"):
                    applied_updates = 0
                    applied_inserts = 0
                    skipped_duplicates = 0
                    with session_scope() as s2:
                        for rule_id, pattern, cat_id_r, rtype_r, priority_r, is_active_r in updates:
                            exact_duplicate, _ = _find_duplicate_and_conflict(
                                s2, pattern, rtype_r, family_member_id, cat_id_r, exclude_rule_id=rule_id
                            )
                            if exact_duplicate:
                                skipped_duplicates += 1
                                continue
                            r = s2.get(Rule, rule_id)
                            r.pattern = pattern
                            r.category_id = cat_id_r
                            r.rule_type = RuleType(rtype_r)
                            r.priority = priority_r
                            r.is_active = is_active_r
                            applied_updates += 1
                        for pattern, cat_id_r, rtype_r, priority_r, is_active_r in inserts:
                            exact_duplicate, _ = _find_duplicate_and_conflict(
                                s2, pattern, rtype_r, family_member_id, cat_id_r
                            )
                            if exact_duplicate:
                                skipped_duplicates += 1
                                continue
                            s2.add(
                                Rule(
                                    rule_type=RuleType(rtype_r), pattern=pattern, category_id=cat_id_r,
                                    priority=priority_r, is_active=is_active_r, family_member_id=family_member_id,
                                )
                            )
                            applied_inserts += 1
                    # st.rerun() stays outside the "with" block — same fix as
                    # the save/add buttons above; calling it inside would
                    # roll back everything we just applied.
                    st.success(
                        f"تم تطبيق الملف: {applied_updates} تحديث، {applied_inserts} قاعدة جديدة"
                        + (f"، تم تجاهل {skipped_duplicates} لأنها مكررة." if skipped_duplicates else ".")
                    )
                    st.rerun()
