import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/gcs_test")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-longer-than-32-characters")
