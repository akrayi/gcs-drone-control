from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from app.security import authorize


@pytest.mark.parametrize("body", [{}, {"result": False}, {"result": "true"}, {"result": 1}])
def test_policy_must_explicitly_return_boolean_true(monkeypatch, body):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json=body, request=httpx.Request("POST", "http://opa")))
    with pytest.raises(HTTPException) as error:
        authorize(SimpleNamespace(username="x", role="admin", active=True), "TAKEOFF")
    assert error.value.status_code == 403


def test_policy_unavailable_fails_closed(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "post", fail)
    with pytest.raises(HTTPException) as error:
        authorize(SimpleNamespace(username="x", role="admin", active=True), "TAKEOFF")
    assert error.value.status_code == 503
