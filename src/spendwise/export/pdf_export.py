"""
Generates an Arabic RTL PDF monthly report using reportlab + the bundled
Amiri font (correct shaping via export.arabic_text.shape_arabic).
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from spendwise.export.arabic_text import shape_arabic

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "fonts")
_FONT_REGULAR = "Amiri-Regular"
_FONT_BOLD = "Amiri-Bold"

_fonts_registered = False


def _ensure_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")))
    _fonts_registered = True


def _ar(text) -> str:
    return shape_arabic(str(text))


def generate_pdf_report(output_path: str, family_member_name: str, metrics, comparison, observations, budget_status=None) -> str:
    _ensure_fonts()

    title_style = ParagraphStyle("title", fontName=_FONT_BOLD, fontSize=18, alignment=2, leading=24)
    heading_style = ParagraphStyle("heading", fontName=_FONT_BOLD, fontSize=13, alignment=2, spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle("body", fontName=_FONT_REGULAR, fontSize=10, alignment=2, leading=16)

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    story = []

    story.append(Paragraph(_ar(f"تقرير المصروفات الشهري — {family_member_name}"), title_style))
    story.append(Paragraph(_ar(f"الشهر: {metrics.month}"), body_style))
    story.append(Spacer(1, 12))

    story.append(Paragraph(_ar("الملخص العام"), heading_style))
    summary_rows = [
        [_ar("إجمالي المصروفات"), f"{metrics.total_expenses:.2f}"],
        [_ar("إجمالي الدخل"), f"{metrics.total_income:.2f}"],
        [_ar("صافي الادخار"), f"{metrics.net_savings:.2f}"],
        [_ar("إجمالي التحويلات (مستثناة من الحسابات)"), f"{metrics.transfers_total:.2f}"],
    ]
    if budget_status and budget_status.budget_amount is not None:
        summary_rows.append([_ar("الميزانية الشهرية"), f"{budget_status.budget_amount:.2f}"])
        if budget_status.remaining is not None:
            summary_rows.append([_ar("المتبقي من الميزانية"), f"{budget_status.remaining:.2f}"])

    summary_table = Table(summary_rows, colWidths=[10 * cm, 6 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 12))

    if metrics.category_totals:
        story.append(Paragraph(_ar("التفصيل حسب التصنيف"), heading_style))
        cat_rows = [[_ar("التصنيف"), _ar("المبلغ")]]
        for cat_id, amount in sorted(metrics.category_totals.items(), key=lambda kv: kv[1], reverse=True):
            name = metrics.category_names.get(cat_id, "غير مصنّف")
            cat_rows.append([_ar(name), f"{amount:.2f}"])
        cat_table = Table(cat_rows, colWidths=[10 * cm, 6 * cm])
        cat_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _FONT_REGULAR),
                    ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ]
            )
        )
        story.append(cat_table)
        story.append(Spacer(1, 12))

    if observations:
        story.append(Paragraph(_ar("ملاحظات وتوصيات"), heading_style))
        for obs in observations:
            story.append(Paragraph(_ar(f"• {obs.text_ar}"), body_style))
        story.append(Spacer(1, 12))

    footer_style = ParagraphStyle("footer", fontName=_FONT_REGULAR, fontSize=8, alignment=2, textColor=colors.grey)
    story.append(
        Paragraph(
            _ar("هذا التقرير لا يحتوي على أي بيانات حساسة أو معلومات تعريفية شخصية، وهو مُخصّص لاستخدامك الشخصي فقط."),
            footer_style,
        )
    )

    doc.build(story)
    return output_path
