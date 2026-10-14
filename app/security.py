import hashlib
import hmac
import os
import time
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    it = settings.pbkdf2_iterations
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, it)
    return f"pbkdf2_sha256${it}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


def create_token(username: str) -> str:
    now = int(time.time())
    payload = {"sub": username, "iat": now, "exp": now + settings.token_expire_minutes * 60}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> str:
    """Retorna o username ou levanta jwt.PyJWTError."""
    data = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    sub = data.get("sub")
    if not sub:
        raise jwt.InvalidTokenError("sem sub")
    return sub


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    if not creds:
        raise _unauthorized("Token ausente")
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise _unauthorized("Token inválido ou expirado")


def current_user_flex(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    token: Optional[str] = Query(default=None, description="Token via query (para EventSource)"),
) -> str:
    raw = creds.credentials if creds else token
    if not raw:
        raise _unauthorized("Token ausente")
    try:
        return decode_token(raw)
    except jwt.PyJWTError:
        raise _unauthorized("Token inválido ou expirado")
