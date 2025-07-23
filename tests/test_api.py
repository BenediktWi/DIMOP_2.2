# flake8: noqa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # noqa: E402

import httpx
from httpx import ASGITransport
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
import backend
import pytest


@pytest.fixture
async def async_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE materials (id INTEGER PRIMARY KEY, name VARCHAR, description VARCHAR)"
            )
        )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    backend.initialize_engine(engine)
    backend.ENGINES["test"] = engine

    from fastapi import Header

    def override_get_db(project_id: str = Header("test", alias="X-Project")):
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    backend.app.dependency_overrides[backend.get_db] = override_get_db
    transport = ASGITransport(app=backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    backend.app.dependency_overrides.clear()


@pytest.fixture
async def async_client_missing_columns():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE materials (id INTEGER PRIMARY KEY, name VARCHAR, description VARCHAR)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE components (id INTEGER PRIMARY KEY, name VARCHAR, material_id INTEGER)"
            )
        )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    backend.initialize_engine(engine)
    backend.ENGINES["test"] = engine

    from fastapi import Header

    def override_get_db(project_id: str = Header("test", alias="X-Project")):
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    backend.app.dependency_overrides[backend.get_db] = override_get_db
    transport = ASGITransport(app=backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    backend.app.dependency_overrides.clear()


@pytest.mark.anyio("asyncio")
async def test_create_and_read_materials(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Project": "test",
    }

    resp = await async_client.post(
        "/materials", json={"name": "Steel"}, headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Steel"

    resp = await async_client.get("/materials", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Steel"


@pytest.mark.anyio("asyncio")
async def test_startup_adds_component_columns(async_client_missing_columns):
    login = await async_client_missing_columns.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Project": "test",
    }

    resp = await async_client_missing_columns.post(
        "/materials", json={"name": "Steel"}, headers=headers
    )
    material_id = resp.json()["id"]

    resp = await async_client_missing_columns.post(
        "/components",
        json={"name": "Root", "material_id": material_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data

    inspector = backend.inspect(backend.ENGINES["test"])
    cols = [c["name"] for c in inspector.get_columns("components")]
    assert "level" in cols


@pytest.mark.anyio("asyncio")
async def test_projects_endpoint(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await async_client.get("/projects", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []
