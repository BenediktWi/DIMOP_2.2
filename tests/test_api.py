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
    backend.engine = engine
    backend.SessionLocal = TestingSessionLocal
    backend.PROJECT_DATABASES = {"1": TestingSessionLocal}
    backend.on_startup()

    transport = ASGITransport(app=backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    backend.PROJECT_DATABASES = {}


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
    backend.engine = engine
    backend.SessionLocal = TestingSessionLocal
    backend.PROJECT_DATABASES = {"1": TestingSessionLocal}
    backend.on_startup()
    transport = ASGITransport(app=backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    backend.PROJECT_DATABASES = {}


@pytest.fixture
async def async_client_projects():
    """Client with two project databases."""
    engine1 = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    engine2 = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for engine in (engine1, engine2):
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE TABLE materials (id INTEGER PRIMARY KEY, name VARCHAR, description VARCHAR)"
                )
            )
    Session1 = sessionmaker(bind=engine1, autoflush=False, autocommit=False)
    Session2 = sessionmaker(bind=engine2, autoflush=False, autocommit=False)

    backend.engine = engine1
    backend.SessionLocal = Session1
    backend.PROJECT_DATABASES = {"1": Session1, "2": Session2}
    backend.on_startup()

    prev_engine = backend.engine
    prev_session = backend.SessionLocal
    backend.engine = engine2
    backend.SessionLocal = Session2
    backend.on_startup()
    backend.engine = prev_engine
    backend.SessionLocal = prev_session

    transport = ASGITransport(app=backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    backend.PROJECT_DATABASES = {}


@pytest.mark.anyio("asyncio")
async def test_create_and_read_materials(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Project": "1"}

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
    headers = {"Authorization": f"Bearer {token}", "X-Project": "1"}

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

    inspector = backend.inspect(backend.engine)
    cols = [c["name"] for c in inspector.get_columns("components")]
    assert "level" in cols


@pytest.mark.anyio("asyncio")
async def test_project_isolation(async_client_projects):
    login = await async_client_projects.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token}", "X-Project": "1"}
    headers2 = {"Authorization": f"Bearer {token}", "X-Project": "2"}

    resp = await async_client_projects.post(
        "/materials",
        json={"name": "Steel"},
        headers=headers1,
    )
    material_id = resp.json()["id"]

    await async_client_projects.post(
        "/components",
        json={"name": "Root", "material_id": material_id},
        headers=headers1,
    )

    resp = await async_client_projects.get("/materials", headers=headers2)
    assert resp.json() == []
    resp = await async_client_projects.get("/components", headers=headers2)
    assert resp.json() == []

    resp = await async_client_projects.get("/materials", headers=headers1)
    assert len(resp.json()) == 1
    resp = await async_client_projects.get("/components", headers=headers1)
    assert len(resp.json()) == 1
