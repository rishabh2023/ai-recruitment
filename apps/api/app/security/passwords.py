"""Password hashing using the standard library only (no external dependency).

Format is Django-compatible: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``. PBKDF2-HMAC
is available everywhere Python runs (including the slim Docker image) and needs no wheel.
Verification is constant-time via ``hmac.compare_digest``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    """Return an encoded hash for ``password``. A fresh random salt is used each call."""
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGORITHM}${iterations}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-time check of ``password`` against a stored ``encoded`` hash.

    Returns ``False`` (rather than raising) for missing or malformed hashes so callers can
    treat "no password set" and "wrong password" identically.
    """
    if not encoded:
        return False
    try:
        algorithm, iterations_s, salt_s, hash_s = encoded.split("$")
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_s)
        salt = _unb64(salt_s)
        expected = _unb64(hash_s)
    except (ValueError, base64.binascii.Error):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)
