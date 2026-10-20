from datetime import datetime, timedelta, timezone
import httpx
import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from .config import settings
from .db import User

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("not-an-actual-user-password")


def issue_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user.username, "ver": user.auth_version,
                       "iat": now, "exp": now + timedelta(minutes=settings.token_minutes),
                       "iss": settings.jwt_issuer, "aud": settings.jwt_audience},
                      settings.jwt_secret, algorithm="HS256")


def authenticate(db, token):
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                            issuer=settings.jwt_issuer, audience=settings.jwt_audience,
                            options={"require": ["sub", "ver", "iat", "exp", "iss", "aud"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, claims["sub"])
    if not user or not user.active or user.auth_version != claims["ver"]:
        raise HTTPException(401, "Session revoked")
    return user


def authorize(user, action):
    try:
        response = httpx.post(f"{settings.opa_url}/v1/data/gcs/authz/allow", timeout=2,
                              json={"input": {"subject": {"username": user.username,
                                    "role": user.role, "active": user.active},
                                    "action": action, "resource": "shared-drone"}})
        response.raise_for_status()
        allowed = response.json().get("result") is True
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(503, "Policy service unavailable; access denied")
    if not allowed:
        raise HTTPException(403, "Policy denied this action")
