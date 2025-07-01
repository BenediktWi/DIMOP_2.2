# flake8: noqa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # noqa: E402

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
import backend
import pytest


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    backend.engine = engine
    backend.SessionLocal = TestingSessionLocal
    backend.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    backend.app.dependency_overrides[backend.get_db] = override_get_db
    with TestClient(backend.app) as c:
        yield c
    backend.app.dependency_overrides.clear()


def test_create_and_read_materials(client):
    resp = client.post("/materials", json={"name": "Steel"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Steel"

    resp = client.get("/materials")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Steel"
