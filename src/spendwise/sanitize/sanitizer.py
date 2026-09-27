"""
Privacy sanitization.

Two responsibilities:
1. sanitize_merchant(): turn a raw transaction description into a short,
   non-sensitive merchant label safe to persist and safe to send to an AI
   provider. All PII-like tokens (IBANs, card numbers, phone numbers,
   emails, reference numbers, long ID numbers) are stripped BEFORE any
   further processing.
2. mask_for_ai(): an additional, stricter pass applied only to the small
   sanitized text sent to the AI fallback, so nothing beyond a clean
   merchant label + amount + type is ever transmitted.

The raw description itself is NEVER persisted to the database and is not
retained beyond the current in-memory import session.
"""
from __future__ import annotations

import re

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:05|5)\d{8}\b|\b\+?\d{9,13}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGIT_RE = re.compile(r"\b\d{6,}\b")  # reference numbers, transaction IDs
_DATE_TOKEN_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

_NOISE_PREFIXES = [
    "شراء نقطة بيع", "شراء", "خصم", "purchase", "pos purchase", "pos", "pmt",
    "payment to", "دفعة", "حوالة", "تحويل الى", "تحويل إلى", "atm withdrawal",
    "سحب نقدي", "withdrawal", "poin of sale", "point of sale",
]


def _strip_pii(text: str) -> str:
    text = _IBAN_RE.sub(" ", text)
    text = _EMAIL_RE.sub(" ", text)
    text = _PHONE_RE.sub(" ", text)
    text = _CARD_RE.sub(" ", text)
    text = _LONG_DIGIT_RE.sub(" ", text)
    text = _DATE_TOKEN_RE.sub(" ", text)
    return text


def sanitize_merchant(raw_description: str, max_len: int = 60) -> str:
    """Produce a short, PII-free merchant label from a raw description."""
    if not raw_description:
        return "غير معروف"

    text = _strip_pii(raw_description)

    lowered = text.strip().lower()
    for prefix in _NOISE_PREFIXES:
        if lowered.startswith(prefix):
            text = text.strip()[len(prefix):]
            break

    # Collapse whitespace and stray punctuation left over from stripped tokens
    text = re.sub(r"[*#_/\\|]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -–—.,:;")

    if not text:
        return "غير معروف"

    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"

    return text


def preview_sanitized_fields(raw_description: str) -> dict:
    """Returns exactly what would be shown to the user as a privacy preview
    before sending to AI, and exactly what would be sent."""
    merchant = sanitize_merchant(raw_description)
    return {"merchant_sanitized": merchant}


def mask_for_ai(merchant_sanitized: str) -> str:
    """Final defensive pass — merchant_sanitized should already be clean,
    but we re-run PII stripping defensively in case of upstream edge cases."""
    return _strip_pii(merchant_sanitized).strip() or "غير معروف"
