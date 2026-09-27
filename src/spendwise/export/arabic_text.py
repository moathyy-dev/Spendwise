"""
Correct Arabic RTL glyph shaping/ordering for use inside reportlab PDFs
(reportlab does not do this automatically).
"""
from __future__ import annotations

import arabic_reshaper
from bidi.algorithm import get_display

_reshaper = arabic_reshaper.ArabicReshaper()


def shape_arabic(text: str) -> str:
    if not text:
        return ""
    reshaped = _reshaper.reshape(str(text))
    return get_display(reshaped)
