"""
One-way fingerprints used to (a) prevent importing the same file twice and
(b) score potential duplicate transactions — without ever storing anything
that could reconstruct the original content.
"""
from __future__ import annotations

import hashlib
import hmac
import os

_SALT_ENV_VAR = "SPENDWISE_FINGERPRINT_SALT"
_DEFAULT_SALT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", ".fingerprint_salt")


def _get_salt() -> bytes:
    """A local, machine-specific salt so fingerprints are not comparable
    across installations and cannot be reversed via rainbow tables. It is
    generated once and stored locally (not a secret key for encryption,
    just a hashing salt — it never leaves the machine)."""
    salt = os.environ.get(_SALT_ENV_VAR)
    if salt:
        return salt.encode("utf-8")

    salt_path = os.path.abspath(_DEFAULT_SALT_FILE)
    os.makedirs(os.path.dirname(salt_path), exist_ok=True)
    if os.path.exists(salt_path):
        with open(salt_path, "rb") as f:
            return f.read()
    new_salt = os.urandom(32)
    with open(salt_path, "wb") as f:
        f.write(new_salt)
    return new_salt


def fingerprint_file_bytes(content: bytes) -> str:
    """One-way hash of raw file bytes. Cannot be used to reconstruct the file."""
    return hmac.new(_get_salt(), content, hashlib.sha256).hexdigest()


def fingerprint_row(date_str: str, amount_str: str, direction: str, account_alias: str, merchant_sanitized: str) -> str:
    """One-way hash of the non-sensitive fields used for duplicate scoring.
    Never includes raw description or any PII."""
    payload = f"{date_str}|{amount_str}|{direction}|{account_alias}|{merchant_sanitized}".encode("utf-8")
    return hmac.new(_get_salt(), payload, hashlib.sha256).hexdigest()
