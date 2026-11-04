import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="routewise-test-")
os.environ["DATABASE_PATH"] = os.path.join(_TMP, "test.db")
os.environ.pop("META_API_KEY", None)
os.environ.pop("META_MODEL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import connect, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_database  # noqa: E402

TABLES = ("vehicles", "defects", "restrictions", "inspections", "repairs", "evidence_analyses")


def reset_db():
    init_db()
    with connect() as c:
        for t in TABLES:
            c.execute(f"DELETE FROM {t}")
    seed_database()


def snapshot():
    """Full dump of every table, for 'database unchanged' assertions."""
    with connect() as c:
        return {t: [tuple(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()] for t in TABLES}


@pytest.fixture(autouse=True)
def _fresh_db():
    app.dependency_overrides.clear()
    reset_db()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def vehicles(client):
    return {v["id"]: v for v in client.get("/vehicles").json()}
