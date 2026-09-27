"""RTL CSS injected once into every page for correct Arabic layout."""
from __future__ import annotations

RTL_CSS = """
<style>
html, body, [class*="css"] { direction: rtl; }
.stApp { direction: rtl; }
section[data-testid="stSidebar"] { direction: rtl; text-align: right; }
div[data-testid="stMetric"] { text-align: right; }
div[role="radiogroup"] { direction: rtl; }
table { direction: rtl; }
.stDataFrame { direction: rtl; }
div[data-testid="stMarkdownContainer"] { text-align: right; }
label { text-align: right; display: block; }
input, textarea { text-align: right; }
.stButton>button { direction: rtl; }
</style>
"""
