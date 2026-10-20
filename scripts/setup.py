"""Cross-platform equivalent of setup.ps1; never prints generated secrets."""
from pathlib import Path
import secrets

path = Path(__file__).resolve().parent.parent / ".env"
with path.open("x", encoding="utf-8") as file:
    for key in ["POSTGRES_PASSWORD", "GCS_DB_PASSWORD", "JWT_SECRET", "BOOTSTRAP_ADMIN_PASSWORD"]:
        file.write(f"{key}={secrets.token_hex(32)}\n")
try:
    path.chmod(0o600)
except OSError:
    pass
print("Created .env. Username: admin. Read BOOTSTRAP_ADMIN_PASSWORD locally in .env.")
