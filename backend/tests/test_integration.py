"""Real PostgreSQL + real OPA. No SQLite substitute for row-lock tests."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.config import settings
from app.db import Base, CommandLog, Drone, Session, User, engine
from app.main import app
from app.manage import initialize
from app.security import issue_token, passwords

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires dedicated PostgreSQL gcs_test and OPA")


@pytest.fixture(autouse=True)
def database():
    if engine.url.database != "gcs_test":
        pytest.fail("Refusing destructive tests outside dedicated gcs_test database")
    for _ in range(30):
        try:
            if httpx.get(settings.opa_url + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.2)
    initialize()
    with Session.begin() as db:
        db.execute(delete(CommandLog))
        db.execute(delete(User))
        d = db.get(Drone, 1)
        d.version, d.mode, d.x, d.y, d.altitude, d.safety_latched = 0, "GROUNDED", 0, 0, 0, False
        for name, role in [("admin", "admin"), ("pilot1", "pilot"), ("pilot2", "pilot"), ("viewer", "viewer")]:
            db.add(User(username=name, role=role, password_hash=passwords.hash("testing-password-123")))
    yield


def headers(name):
    with Session() as db:
        return {"Authorization": "Bearer " + issue_token(db.get(User, name))}


def payload(action, version=0, **extra):
    return {"request_id": str(uuid4()), "action": action, "expected_version": version, **extra}


def race(commands):
    barrier = Barrier(len(commands))
    def worker(item):
        name, body = item
        auth = headers(name)
        # Separate clients, threadpool workers, SQL sessions and DB connections.
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return client.post("/api/commands", headers=auth, json=body)
    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        return list(pool.map(worker, commands))


@pytest.mark.parametrize("order", [False, True])
def test_simultaneous_takeoff_return_home(order):
    commands = [("pilot1", payload("TAKEOFF")), ("pilot2", payload("RETURN_HOME"))]
    results = race(commands[::-1] if order else commands)
    assert all(r.status_code in (200, 409) for r in results)
    with Session() as db:
        d = db.get(Drone, 1)
        assert (d.mode, d.altitude, d.safety_latched) == ("GROUNDED", 0, True)
        assert len(db.scalars(select(CommandLog)).all()) == 2


def test_simultaneous_takeoff_only_one_commits():
    results = race([("pilot1", payload("TAKEOFF")), ("pilot2", payload("TAKEOFF"))])
    assert sorted(r.status_code for r in results) == [200, 409]
    with Session() as db:
        assert db.get(Drone, 1).version == 1


def test_duplicate_concurrent_request_exactly_once():
    body = payload("TAKEOFF")
    results = race([("pilot1", body), ("pilot1", body)])
    assert results[0].json() == results[1].json()
    with Session() as db:
        assert db.get(Drone, 1).version == 1
        assert len(db.scalars(select(CommandLog)).all()) == 1


def test_grounded_home_and_viewer_denial():
    with TestClient(app) as client:
        with Session.begin() as db:
            d = db.get(Drone, 1)
            d.x, d.y = 32, -9
        assert client.post("/api/commands", headers=headers("viewer"), json=payload("TAKEOFF")).status_code == 403
        result = client.post("/api/commands", headers=headers("pilot1"), json=payload("RETURN_HOME")).json()["state"]
        assert (result["x"], result["y"], result["altitude"]) == (32, -9, 0)
        assert client.post("/api/commands", headers=headers("pilot1"), json=payload("CLEAR_SAFETY", 1)).status_code == 403


def test_idempotency_key_cannot_be_reused_by_other_user_or_payload():
    with TestClient(app) as client:
        body = payload("TAKEOFF")
        assert client.post("/api/commands", headers=headers("pilot1"), json=body).status_code == 200
        assert client.post("/api/commands", headers=headers("pilot2"), json=body).status_code == 409
        assert client.post("/api/commands", headers=headers("pilot1"), json={**body, "action": "LAND"}).status_code == 409


def test_admin_user_lifecycle_and_session_revocation():
    with TestClient(app) as client:
        admin = headers("admin")
        body = {"username": "newpilot", "password": "long-initial-password", "role": "pilot"}
        assert client.post("/api/users", headers=headers("pilot1"), json=body).status_code == 403
        assert client.post("/api/users", headers=admin, json=body).status_code == 201
        assert client.post("/api/users", headers=admin, json=body).status_code == 409
        login = client.post("/api/auth/login", json={"username": body["username"], "password": body["password"]})
        old = {"Authorization": "Bearer " + login.json()["access_token"]}
        assert client.get("/api/state", headers=old).status_code == 200
        assert client.post("/api/users/newpilot", headers=admin, json={"role": "viewer"}).status_code == 200
        assert client.get("/api/state", headers=old).status_code == 401
        assert client.post("/api/users/newpilot", headers=admin, json={"password": "replacement-password"}).status_code == 200
        assert client.post("/api/auth/login", json={"username": body["username"], "password": body["password"]}).status_code == 401
        assert client.post("/api/users/newpilot", headers=admin, json={"active": False}).status_code == 200
        assert client.post("/api/auth/login", json={"username": "newpilot", "password": "replacement-password"}).status_code == 401
        assert client.post("/api/users/admin", headers=admin, json={"active": False}).status_code == 409


def test_websocket_sync_origin_and_revocation():
    with TestClient(app) as client:
        auth = headers("pilot1")
        with client.websocket_connect("/api/ws", headers={"origin": "http://localhost:8080"}) as ws:
            ws.send_json({"token": auth["Authorization"].split()[1]})
            assert ws.receive_json()["state"]["version"] == 0
            client.post("/api/commands", headers=headers("pilot2"), json=payload("TAKEOFF"))
            for _ in range(10):
                data = ws.receive_json()
                if data["state"]["version"] == 1:
                    break
            assert data["state"]["mode"] == "AIRBORNE"
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws", headers={"origin": "https://evil.example"}):
                pass


def test_login_lockout_and_expired_jwt():
    with TestClient(app) as client:
        for _ in range(5):
            assert client.post("/api/auth/login", json={"username": "pilot1", "password": "wrong"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "pilot1", "password": "testing-password-123"}).status_code == 429
        now = datetime.now(timezone.utc)
        expired = jwt.encode({"sub": "viewer", "ver": 1, "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1),
                              "iss": settings.jwt_issuer, "aud": settings.jwt_audience}, settings.jwt_secret, algorithm="HS256")
        assert client.get("/api/state", headers={"Authorization": "Bearer " + expired}).status_code == 401


def test_state_and_receipt_rollback_together():
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    def fail_commit(session, flush_context, instances):
        if any(isinstance(item, CommandLog) for item in session.new):
            raise OperationalError("simulated write failure", None, Exception("unavailable"))
    event.listen(Session.class_, "before_flush", fail_commit)
    try:
        with TestClient(app) as client:
            result = client.post("/api/commands", headers=headers("pilot1"), json=payload("TAKEOFF"))
            assert result.status_code == 503
    finally:
        event.remove(Session.class_, "before_flush", fail_commit)
    with Session() as db:
        assert (db.get(Drone, 1).version, db.get(Drone, 1).mode) == (0, "GROUNDED")
        assert db.scalars(select(CommandLog)).all() == []


def test_open_websocket_closes_after_user_disabled():
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app) as client:
        auth = headers("pilot1")
        with client.websocket_connect("/api/ws", headers={"origin": "http://localhost:8080"}) as ws:
            ws.send_json({"token": auth["Authorization"].split()[1]})
            assert ws.receive_json()["user"]["username"] == "pilot1"
            assert client.post("/api/users/pilot1", headers=headers("admin"), json={"active": False}).status_code == 200
            with pytest.raises(WebSocketDisconnect) as disconnected:
                for _ in range(10):
                    ws.receive_json()
            assert disconnected.value.code == 1008
