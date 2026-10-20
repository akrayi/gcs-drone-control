# Local development and testing

[Back to the project](../README.md)

## Run locally with Docker

Install Docker Desktop with Linux containers and Docker Compose v2. From this
project's root, in PowerShell:

```powershell
# Only needed if .env has not already been generated:
./scripts/setup.ps1

docker compose up --build -d
docker compose ps
docker compose logs init
```

On macOS/Linux, use `python3 scripts/setup.py` for the credential-generation step.
The scripts refuse to overwrite an existing `.env`. Every new clone needs its own `.env`; this file is never stored in Git.

Open **http://localhost:8080**. Username: **admin**. Read the generated
`BOOTSTRAP_ADMIN_PASSWORD` value in your local `.env` file. There is no shared,
hardcoded password. The initial password is 64 random hexadecimal characters.

Sign in, then use **Operators & access** to create `pilot1`, `pilot2`, and `viewer`
with distinct passwords of at least 12 characters. Open separate browser profiles
or incognito windows to observe synchronized dashboards. Tokens remain only in
browser memory, so reloading requires signing in again.

Useful commands:

```powershell
docker compose logs -f backend opa
docker compose restart backend
docker compose down
```

`down` preserves the database volume. Do not add `-v` unless you intend to erase
all users, passwords, command history, and drone state. Re-running the setup
container does not replace existing accounts or change their passwords.

### What starts

1. PostgreSQL initializes its volume and creates the `gcs` database owner.
2. The `init` container creates tables and bootstraps only the admin account.
3. OPA loads the policy independently of the Python backend.
4. The backend becomes ready after PostgreSQL and the OPA decision endpoint work.
5. The frontend exposes one local port. Database, OPA, and API ports stay private.

## Tests

Run the real integration tests against a separate, temporary PostgreSQL database:

```powershell
docker compose --profile test run --build --rm tests
docker compose --profile test run --rm policy-tests
```

The tests service uses `gcs_test`; tests refuse to reset any other database. They
cover simultaneous TAKEOFF/RETURN_HOME, simultaneous takeoffs, duplicate concurrent
requests, grounded safety behavior, stale lock clearing, role denial, user
management, token revocation/expiry, account lockout, and WebSocket synchronization.

For Python-only unit checks with Python 3.12+:

```powershell
python -m venv .venv
./.venv/Scripts/python -m pip install -r backend/requirements.txt
Push-Location backend
../.venv/Scripts/python -m pytest tests/test_domain.py tests/test_security.py -q
Pop-Location
```

For frontend development, use Node 22+, run `npm ci` then `npm run dev` in
`frontend/`, and run the backend on port 8000 with `ALLOWED_ORIGINS` including
`http://localhost:5173`. The Vite proxy forwards `/api` and WebSockets. Production
build: `npm run build`. Formatting is available from the root with `npm run format`.
