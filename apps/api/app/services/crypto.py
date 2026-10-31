"""AUTH-03: AES-256-GCM for OAuth tokens and TOTP secrets. Ciphertext format: base64(nonce || ct+tag)."""

import base64
import hashlib
import hmac
import os
import struct
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import get_settings


def _key() -> bytes:
    s = get_settings()
    if s.token_key:
        k = base64.b64decode(s.token_key)
        if len(k) != 32:
            raise ValueError("EF_TOKEN_KEY must be 32 bytes, base64-encoded")
        return k
    if s.is_prod:
        raise RuntimeError("EF_TOKEN_KEY is required in prod")
    return HKDF(algorithm=SHA256(), length=32, salt=b"ef-token-key", info=b"v1").derive(s.secret_key.encode())


def encrypt(plain: str) -> str:
    if not plain:
        return ""
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(_key()).encrypt(nonce, plain.encode(), None)).decode()


def decrypt(blob: str) -> str:
    if not blob:
        return ""
    raw = base64.b64decode(blob)
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode()


# ---- TOTP (RFC 6238) for admin MFA ----


def totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp(secret: str, at: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at or time.time()) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_ok(secret: str, code: str, window: int = 1) -> bool:
    now = time.time()
    return any(hmac.compare_digest(totp(secret, now + i * 30), code.strip()) for i in range(-window, window + 1))


def password_hash(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    return base64.b64encode(salt + hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)).decode()


def password_ok(pw: str, stored: str) -> bool:
    if not stored:
        return False
    raw = base64.b64decode(stored)
    return hmac.compare_digest(password_hash(pw, raw[:16]), stored)
