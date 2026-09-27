from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st

from spendwise.analytics.budget import compute_budget_status
from spendwise.analytics.comparisons import compute_comparison
from spendwise.analytics.recommendations import generate_observations
from spendwise.db.session import session_scope


def render():
    st.header("🏠 لوحة المعلومات")
    family_member_id = st.session_state.get("active_family_member_id")
    if family_member_id is None:
        st.warning("يرجى اختيار عضو من الشريط الجانبي أولًا.")
        return

    current_month = dt.date.today().strftime("%Y-%m")
    month = st.text_input("الشهر (YYYY-MM)", value=current_month, key="home_month")

    with session_scope() as session:
        comparison = compute_comparison(session, family_member_id, month)
        metrics = comparison.current
        budget_status = compute_budget_status(session, family_member_id, month, metrics)
        observations = generate_observations(session, family_member_id, comparison, budget_status)

        # Extract plain data while the session is open (avoid detached ORM access later).
        category_totals = dict(metrics.category_totals)
        category_names = dict(metrics.category_names)
        daily_totals = dict(metrics.daily_totals)
        highest_categories = list(metrics.highest_categories)
        highest_merchants = list(metrics.highest_merchants)
        obs_list = [(o.kind, o.text_ar) for o in observations]

    if not metrics.has_sufficient_data:
        st.info(metrics.insufficient_data_reason_ar or "لا تتوفر بيانات كافية لهذا الشهر بعد.")
        return

    if metrics.is_partial_month:
        st.caption("⚠️ هذا الشهر لم يكتمل بعد — الأرقام أدناه مبنية على البيانات المتوفرة حتى الآن فقط.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("إجمالي المصروفات", f"{metrics.total_expenses:.2f}")
    c2.metric("إجمالي الدخل", f"{metrics.total_income:.2f}")
    c3.metric("صافي الادخار", f"{metrics.net_savings:.2f}")
    c4.metric("معاملات بانتظار المراجعة", metrics.pending_review_count)

    st.divider()
    st.subheader("🎯 الميزانية الشهرية")
    if budget_status.budget_amount is None:
        st.info("لم تحدد ميزانية لهذا الشهر بعد — يمكنك تحديدها من صفحة الميزانية.")
    else:
        pct = float(budget_status.consumed_pct) if budget_status.consumed_pct is not None else 0
        st.progress(min(pct / 100, 1.0), text=f"تم استخدام {pct:.0f}% من الميزانية ({budget_status.spent:.2f} من {budget_status.budget_amount:.2f})")
        if budget_status.remaining is not None and budget_status.remaining < 0:
            st.warning(f"تم تجاوز الميزانية بمقدار {abs(budget_status.remaining):.2f}.")
        elif metrics.is_partial_month and budget_status.projected_overrun and budget_status.projected_overrun > 0:
            st.warning(f"بالمعدل الحالي، من المتوقع تجاوز الميزانية بمقدار تقريبي {budget_status.projected_overrun:.2f} بنهاية الشهر.")

    st.divider()
    st.subheader("📊 المقارنة")
    col1, col2 = st.columns(2)
    with col1:
        if comparison.previous is not None:
            delta = comparison.previous_delta_amount
            st.metric("مقارنة بالشهر السابق", f"{comparison.previous.total_expenses:.2f}", delta=f"{delta:+.2f}")
        else:
            st.caption("لا تتوفر بيانات كافية عن الشهر السابق.")
    with col2:
        if comparison.historical_average_expenses is not None:
            delta = comparison.historical_delta_amount
            st.metric("مقارنة بالمتوسط التاريخي", f"{comparison.historical_average_expenses:.2f}", delta=f"{delta:+.2f}")
        else:
            st.caption("لا تتوفر أشهر سابقة كافية لحساب متوسط تاريخي.")
    if comparison.note_ar:
        st.caption(comparison.note_ar)

    st.divider()
    st.subheader("📂 الإنفاق حسب التصنيف")
    if category_totals:
        chart_data = pd.DataFrame(
            [{"التصنيف": category_names.get(cid, "غير مصنّف"), "المبلغ": float(amt)} for cid, amt in category_totals.items() if amt > 0]
        )
        if not chart_data.empty:
            fig = px.pie(chart_data, names="التصنيف", values="المبلغ")
            st.plotly_chart(fig, use_container_width=True)

    if daily_totals:
        st.subheader("📈 الاتجاه اليومي للإنفاق")
        daily_df = pd.DataFrame(sorted(daily_totals.items()), columns=["اليوم", "المبلغ"])
        daily_df["المبلغ"] = daily_df["المبلغ"].astype(float)
        fig2 = px.line(daily_df, x="اليوم", y="المبلغ", markers=True)
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("أعلى التصنيفات")
        for cid, amt in highest_categories:
            st.write(f"• {category_names.get(cid, 'غير مصنّف')}: {amt:.2f}")
    with col4:
        st.subheader("أعلى التجار")
        for merchant, amt in highest_merchants:
            st.write(f"• {merchant}: {amt:.2f}")

    st.divider()
    st.subheader("💡 ملاحظات وتوصيات")
    icons = {"fact": "📌", "estimate": "🔢", "projection": "🔮", "suggestion": "💡"}
    for kind, text in obs_list:
        st.write(f"{icons.get(kind, '•')} {text}")
