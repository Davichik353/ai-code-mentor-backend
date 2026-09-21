"""
Authentication utilities for AI Code Mentor.

Design choices (learned from today's deployment saga):
- Password hashing uses Python's built-in hashlib.pbkdf2_hmac — no extra
  dependency, so no risk of a Rust/C-extension build failing on a fresh
  Render environment (unlike bcrypt/argon2 which sometimes need compilation).
- JWT uses PyJWT, which is pure Python with reliable prebuilt wheels.
"""

import hashlib
import hmac
import os
import re
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv

import jwt

load_dotenv(Path(__file__).resolve().parent / ".env")

# Secret key for signing JWTs. In production this MUST come from an env var —
# falls back to a random one on startup so local dev still works, but that
# means tokens won't survive a server restart unless JWT_SECRET is set.
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days

PBKDF2_ITERATIONS = 260_000  # OWASP-recommended minimum as of 2023+


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random per-user salt.
    Returns a single string: 'salt_hex$hash_hex' so it's self-contained."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a hash produced by hash_password()."""
    try:
        salt_hex, hash_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def create_access_token(user_id: str, email: str) -> str:
    """Create a signed JWT for a user, valid for JWT_EXPIRY_SECONDS."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns the payload dict, or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def is_valid_email(email: str) -> bool:
    """Very small sanity check — not full RFC validation, just catches obvious junk."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)) and len(email) <= 254

DISPOSABLE_EMAIL_DOMAINS = {
    "10minutemail.com", "guerrillamail.com", "mailinator.com",
    "tempmail.com", "temp-mail.org", "yopmail.com", "trashmail.com",
}

def is_disposable_email(email: str) -> bool:
    return email.rsplit("@", 1)[-1].lower() in DISPOSABLE_EMAIL_DOMAINS

def is_strong_password(password: str) -> bool:
    return (
        len(password) >= 10
        and bool(re.search(r"[A-Z]", password))
        and bool(re.search(r"[a-z]", password))
        and bool(re.search(r"\d", password))
        and bool(re.search(r"[^A-Za-z0-9]", password))
    )
