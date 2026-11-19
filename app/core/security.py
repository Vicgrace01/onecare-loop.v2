from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(subject: str, secret_key: str, ttl_seconds: int) -> str:
    serializer = URLSafeTimedSerializer(secret_key, salt="onecare-access-token-v1", signer_kwargs={"digest_method": hashlib.sha256})
    return serializer.dumps({"sub": subject, "iat": int(datetime.now(timezone.utc).timestamp())})


def read_access_token(token: str, secret_key: str, max_age: int) -> dict[str, Any] | None:
    serializer = URLSafeTimedSerializer(secret_key, salt="onecare-access-token-v1", signer_kwargs={"digest_method": hashlib.sha256})
    try:
        payload = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str):
        return None
    return payload
