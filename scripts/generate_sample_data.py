"""
Generates synthetic (fake) sample bank-statement files for testing SpendWise
without ever using real financial data:
  - an Arabic-column Excel file
  - an English-column Excel file
  - a text-based PDF statement

Run: python scripts/generate_sample_data.py
"""
from __future__ import annotations

import os
import random
from datetime import date, timedelta

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "sample_data", "statements")
FONTS_DIR = os.path.join(PROJECT_ROOT, "assets", "fonts")

os.makedirs(OUT_DIR, exist_ok=True)

random.seed(42)

_MERCHANTS_AR = [
    ("شراء نقطة بيع مطعم البيك", -45.50),
    ("شراء نقطة بيع كارفور", -230.75),
    ("STC فوترة", -120.00),
    ("سحب نقدي ATM", -400.00),
    ("تحويل الى حساب آخر", -1000.00),
    ("راتب شهري", 9500.00),
    ("شراء نقطة بيع ستاربكس", -28.00),
    ("شراء نقطة بيع صيدلية النهدي", -65.30),
    ("اشتراك نتفلكس", -45.00),
    ("استرداد مبلغ مطعم البيك", 45.50),
]

_MERCHANTS_EN = [
    ("POS PURCHASE UBER TRIP", -32.10),
    ("POS PURCHASE AMAZON.SA", -156.90),
    ("SALARY TRANSFER", 9500.00),
    ("ATM WITHDRAWAL", -300.00),
    ("TRANSFER TO SAVINGS ACCOUNT", -500.00),
    ("POS PURCHASE NOON.COM", -89.25),
    ("MOBILY BILL PAYMENT", -99.00),
    ("POS PURCHASE PANDA HYPERMARKET", -210.40),
    ("SPOTIFY SUBSCRIPTION", -19.99),
    ("REFUND AMAZON.SA", 156.90),
]


def generate_arabic_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "كشف الحساب"
    ws.append(["التاريخ", "البيان", "مدين", "دائن", "الرصيد"])

    start = date(2026, 8, 1)
    balance = 12000.0
    for i in range(25):
        desc, amount = random.choice(_MERCHANTS_AR)
        d = start + timedelta(days=i)
        debit = abs(amount) if amount < 0 else ""
        credit = amount if amount > 0 else ""
        balance += amount
        ws.append([d.strftime("%d/%m/%Y"), desc, debit, credit, round(balance, 2)])

    path = os.path.join(OUT_DIR, "نموذج_كشف_حساب_عربي.xlsx")
    wb.save(path)
    return path


def generate_english_excel():
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Date", "Description", "Debit", "Credit", "Balance"])

    start = date(2026, 8, 1)
    balance = 8000.0
    for i in range(25):
        desc, amount = random.choice(_MERCHANTS_EN)
        d = start + timedelta(days=i)
        debit = abs(amount) if amount < 0 else ""
        credit = amount if amount > 0 else ""
        balance += amount
        ws.append([d.strftime("%Y-%m-%d"), desc, debit, credit, round(balance, 2)])

    path = os.path.join(OUT_DIR, "sample_statement_english.xlsx")
    wb.save(path)
    return path


def generate_pdf_statement():
    pdfmetrics.registerFont(TTFont("Amiri-Regular", os.path.join(FONTS_DIR, "Amiri-Regular.ttf")))

    from spendwise.export.arabic_text import shape_arabic

    rows = [["التاريخ", "البيان", "المبلغ"]]
    start = date(2026, 8, 1)
    for i in range(15):
        desc, amount = random.choice(_MERCHANTS_AR)
        d = start + timedelta(days=i)
        rows.append([d.strftime("%d/%m/%Y"), shape_arabic(desc), f"{amount:.2f}"])

    path = os.path.join(OUT_DIR, "sample_statement.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    table = Table(rows, colWidths=[4 * cm, 9 * cm, 3 * cm])
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Amiri-Regular"), ("GRID", (0, 0), (-1, -1), 0.5, "grey")]))
    doc.build([table])
    return path


if __name__ == "__main__":
    import sys

    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
    p1 = generate_arabic_excel()
    p2 = generate_english_excel()
    p3 = generate_pdf_statement()
    print("Generated:")
    print(p1)
    print(p2)
    print(p3)
