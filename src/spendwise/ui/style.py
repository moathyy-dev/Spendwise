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

/* The blanket `[class*="css"] { direction: rtl }` rule above also hits the
   internals of Streamlit's slider widget (BaseWeb), whose current-value
   "bubble" above the thumb is positioned with a left/transform calculation
   that assumes an LTR layout. Forcing rtl on those internals breaks that
   math, so the bubble renders off-position/invisible while dragging — only
   the static min/max end labels (plain text, unaffected) stay visible. Reset
   direction to ltr specifically inside the slider so the value bubble shows
   correctly; the widget's own label above it is a separate element and stays
   right-aligned via the `label` rule above. */
div[data-testid="stSlider"], div[data-testid="stSlider"] * { direction: ltr !important; }

/* Same root cause as the slider fix above: the blanket `[class*="css"]`
   rule also reaches Streamlit's own native top toolbar (the "Deploy" button
   and the ⋮ menu, header[data-testid="stHeader"]), which is positioned
   assuming an LTR page. Forcing rtl on it flips its internal layout math,
   so it can render collapsed/overlapped by other top-of-page content
   instead of staying pinned at the top-right corner. Reset it back to ltr
   so it stays in its normal spot; this is purely Streamlit's own hosting
   chrome, not something this app renders, so nothing else here is affected.
   (Note: this toolbar fading in/out as your mouse moves away from the top
   of the page is normal Streamlit behavior, not a bug — only the "hiding
   behind other content" part was the actual issue.) */
header[data-testid="stHeader"], header[data-testid="stHeader"] * { direction: ltr !important; }
</style>
"""
