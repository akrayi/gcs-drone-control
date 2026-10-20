import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from .config import settings
from .db import Session, User
from .domain import Command
from .security import DUMMY_HASH, issue_token, passwords, authenticate, authorize
from typing import Literal
from .service import execute, snapshot

app = FastAPI(title="GCS Zero-Trust Simulator", version="1.0.0")
origins = [o.strip() for o in settings.allowed_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])
bearer = HTTPBearer()


def token(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    return credentials.credentials


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=1, max_length=128)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable or busy; retry with the same request ID"})


@app.get("/api/health/live")
def live():
    return {"status": "alive"}


@app.get("/api/health/ready")
def ready():
    import httpx
    with Session() as db:
        if db.execute(text("SELECT id FROM drone WHERE id=1")).scalar() != 1:
            raise HTTPException(503, "Database not initialized")
    try:
        r = httpx.post(f"{settings.opa_url}/v1/data/gcs/authz/allow", json={"input": {}}, timeout=2)
        r.raise_for_status()
        if r.json().get("result") is not False:
            raise ValueError("Missing deny-by-default policy")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Policy not ready")
    return {"status": "ready"}


@app.post("/api/auth/login")
def login(body: Login):
    result = None
    # Account lockout lives in Postgres, so replicas share the same counter.
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.username == body.username).with_for_update())
        now = datetime.now(timezone.utc)
        if user and user.locked_until and user.locked_until > now:
            raise HTTPException(429, "Account temporarily locked; retry in five minutes")
        valid = passwords.verify(body.password, user.password_hash if user else DUMMY_HASH)
        if user and valid and user.active:
            user.failures, user.locked_until = 0, None
            result = {"access_token": issue_token(user), "token_type": "bearer",
                      "expires_in": settings.token_minutes * 60}
        elif user:
            user.failures += 1
            if user.failures >= 5:
                user.locked_until, user.failures = now + timedelta(minutes=5), 0
    if result is None:
        raise HTTPException(401, "Invalid credentials")
    return result


@app.get("/api/state")
def get_state(access_token: str = Depends(token)):
    return snapshot(access_token)


@app.post("/api/commands")
def command(body: Command, access_token: str = Depends(token)):
    code, result = execute(access_token, body)
    return JSONResponse(status_code=code, content=result)


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "pilot", "viewer"]


class UserUpdate(BaseModel):
    role: Literal["admin", "pilot", "viewer"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)


@app.get("/api/users")
def list_users(access_token: str = Depends(token)):
    with Session() as db:
        actor = authenticate(db, access_token)
        authorize(actor, "USERS_READ")
        return [{"username": u.username, "role": u.role, "active": u.active}
                for u in db.scalars(select(User).order_by(User.username))]


@app.post("/api/users", status_code=201)
def create_user(body: NewUser, access_token: str = Depends(token)):
    from sqlalchemy.exc import IntegrityError
    try:
        with Session.begin() as db:
            actor = authenticate(db, access_token)
            authorize(actor, "USERS_WRITE")
            if db.get(User, body.username):
                raise HTTPException(409, "Username already exists")
            db.add(User(username=body.username, role=body.role, password_hash=passwords.hash(body.password)))
    except IntegrityError:
        raise HTTPException(409, "Username already exists")
    return {"username": body.username, "role": body.role, "active": True}


@app.post("/api/users/{username}")
def update_user(username: str, body: UserUpdate, access_token: str = Depends(token)):
    with Session.begin() as db:
        # Prevent concurrent administrators removing each other and losing all admins.
        db.execute(text("SELECT pg_advisory_xact_lock(800002)"))
        actor = authenticate(db, access_token)
        authorize(actor, "USERS_WRITE")
        user = db.scalar(select(User).where(User.username == username).with_for_update())
        if not user:
            raise HTTPException(404, "User not found")
        if username == actor.username and (body.active is False or body.role not in (None, "admin")):
            raise HTTPException(409, "You cannot disable or demote yourself")
        if user.role == "admin" and user.active and (body.active is False or body.role not in (None, "admin")):
            admins = db.scalars(select(User).where(User.role == "admin", User.active.is_(True))).all()
            if len(admins) <= 1:
                raise HTTPException(409, "At least one active admin is required")
        if body.role is not None:
            user.role = body.role
        if body.active is not None:
            user.active = body.active
        if body.password is not None:
            user.password_hash = passwords.hash(body.password)
            user.failures, user.locked_until = 0, None
        user.auth_version += 1
        return {"username": user.username, "role": user.role, "active": user.active}


@app.websocket("/api/ws")
async def websocket(ws: WebSocket):
    if ws.headers.get("origin") not in origins:
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        # No token in URL, access logs, cookies, or localStorage.
        hello = await asyncio.wait_for(ws.receive_json(), timeout=5)
        access_token = hello.get("token")
        if not isinstance(access_token, str) or len(access_token) > 4096:
            await ws.close(code=1008)
            return
        while True:
            # Shared DB snapshots work across replicas and recover missed updates.
            # Reauthentication and OPA evaluation enforce expiry/revocation on streams.
            data = await asyncio.to_thread(snapshot, access_token)
            await ws.send_json(data)
            await asyncio.sleep(0.5)
    except HTTPException as exc:
        await ws.close(code=1008 if exc.status_code in (401, 403) else 1013)
    except (SQLAlchemyError, OSError):
        await ws.close(code=1013)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (asyncio.TimeoutError, ValueError, AttributeError):
        await ws.close(code=1008)
