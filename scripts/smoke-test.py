"""Check a freshly bootstrapped Compose stack without printing credentials."""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

values = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line)
base = "http://localhost:8080"


def request(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urlopen(req, timeout=10) as response:
        return json.load(response)


with urlopen(base, timeout=10) as response:
    assert "Content-Security-Policy" in response.headers
    assert b'root' in response.read()
assert request("/api/health/ready")["status"] == "ready"
token = request("/api/auth/login", {"username": "admin", "password": values["BOOTSTRAP_ADMIN_PASSWORD"]})["access_token"]
snapshot = request("/api/state", token=token)
assert snapshot["user"]["role"] == "admin"
result = request("/api/commands", {"request_id": str(uuid4()), "action": "RETURN_HOME"}, token)
assert result["state"]["mode"] == "GROUNDED"
assert result["state"]["safety_latched"] is True
request("/api/commands", {"request_id": str(uuid4()), "action": "CLEAR_SAFETY", "expected_version": result["state"]["version"]}, token)
print("Docker smoke test passed: frontend security headers, readiness, bootstrap login, shared state and safety commands.")
