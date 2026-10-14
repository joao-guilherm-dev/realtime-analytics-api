import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["PBKDF2_ITERATIONS"] = "1000"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["SECRET_KEY"] = "test-secret-key-with-more-than-32-characters!!"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    client.post("/api/v1/auth/register", json={"username": "tester", "password": "senha12345"})
    r = client.post("/api/v1/auth/login", json={"username": "tester", "password": "senha12345"})
    return r.json()["access_token"]


@pytest.fixture()
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def metric():
    return "t_" + uuid.uuid4().hex[:10]


def make_points(metric, values, start=1_700_000_000.0, step=1.0):
    return {"points": [{"metric": metric, "value": v, "timestamp": start + i * step} for i, v in enumerate(values)]}
