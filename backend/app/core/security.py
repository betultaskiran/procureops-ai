"""
app/core/security.py

Security primitives for ProcureOps AI:
- Password hashing and verification using bcrypt (with strict 72-byte UTF-8 boundary checks).
- JWT token generation and decoding using pyjwt (with required exp claim enforcement).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# Bcrypt algorithm natively truncates or errors on inputs exceeding 72 bytes.
# We explicitly reject inputs exceeding 72 UTF-8 bytes to prevent silent truncation
# and unhandled runtime exceptions.
MAX_PASSWORD_BYTES: int = 72


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with automatic salt generation.
    Enforces a strict 72-byte UTF-8 limit. Never silently truncates.
    Returns the hashed password as an ASCII string.
    """
    if not password:
        raise ValueError("Password cannot be empty")

    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password cannot exceed {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
        )

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    Safely returns False on mismatch, corrupted hash, or if plain_password
    exceeds 72 bytes (since no valid hash could have been created).
    """
    if not plain_password or not hashed_password:
        return False

    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > MAX_PASSWORD_BYTES:
        return False

    try:
        return bcrypt.checkpw(
            pwd_bytes,
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Create a signed JWT access token containing the provided claims.
    Standard claims added: 'exp' (expiration), 'iat' (issued at).
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.
    Enforces required 'exp' claim to prevent indefinite tokens.
    Raises jwt.ExpiredSignatureError if token is expired.
    Raises jwt.PyJWTError on missing claims, invalid signature, or malformed token.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp"]},
    )
