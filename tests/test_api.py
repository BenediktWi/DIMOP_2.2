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
        connect_args={"check_same_thread": False, "foreign_keys": 1},
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
    backend.on_startup()

    def override_get_db():
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
async def async_client_full_schema():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False, "foreign_keys": 1},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    backend.engine = engine
    backend.SessionLocal = TestingSessionLocal
    backend.on_startup()

    def override_get_db():
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
        connect_args={"check_same_thread": False, "foreign_keys": 1},
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
    backend.on_startup()

    def override_get_db():
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
    headers = {"Authorization": f"Bearer {token}"}

    proj_resp = await async_client.post(
        "/projects", json={"name": "Proj"}, headers=headers
    )
    project_id = proj_resp.json()["id"]

    resp = await async_client.post(
        "/materials",
        json={"name": "Steel", "project_id": project_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Steel"

    resp = await async_client.get(
        "/materials",
        params={"project_id": project_id},
        headers=headers,
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Steel"


@pytest.mark.anyio("asyncio")
async def test_update_material_density_no_project_id(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_resp = await async_client.post(
        "/projects", json={"name": "Proj"}, headers=headers
    )
    project_id = proj_resp.json()["id"]

    resp = await async_client.post(
        "/materials",
        json={"name": "Holz", "project_id": project_id, "density": 1.0},
        headers=headers,
    )
    material_id = resp.json()["id"]

    resp = await async_client.put(
        f"/materials/{material_id}",
        json={"density": 0.8},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["density"] == 0.8


@pytest.mark.anyio("asyncio")
async def test_startup_adds_component_columns(async_client_missing_columns):
    login = await async_client_missing_columns.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_resp = await async_client_missing_columns.post(
        "/projects", json={"name": "Proj"}, headers=headers
    )
    project_id = proj_resp.json()["id"]

    resp = await async_client_missing_columns.post(
        "/materials",
        json={"name": "Steel", "project_id": project_id},
        headers=headers,
    )
    material_id = resp.json()["id"]

    resp = await async_client_missing_columns.post(
        "/components",
        json={
            "name": "Root",
            "material_id": material_id,
            "project_id": project_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data

    inspector = backend.inspect(backend.engine)
    cols = [c["name"] for c in inspector.get_columns("components")]
    assert "level" in cols

    mat_cols = [c["name"] for c in inspector.get_columns("materials")]
    assert "total_gwp" in mat_cols
    assert "fossil_gwp" in mat_cols
    assert "biogenic_gwp" in mat_cols
    assert "adpf" in mat_cols
    assert "density" in mat_cols
    assert "is_dangerous" in mat_cols
    assert "plast_fam" in mat_cols
    assert "mara_plast_id" in mat_cols

    tables = inspector.get_table_names()
    assert "sys_sort" in tables
    assert "plast" in tables
    assert "rel" in tables
    assert "compability" in tables


@pytest.mark.anyio("asyncio")
async def test_duplicate_material_name_returns_400(async_client_full_schema):
    login = await async_client_full_schema.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_resp = await async_client_full_schema.post(
        "/projects",
        json={"name": "Proj"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    first = await async_client_full_schema.post(
        "/materials",
        json={"name": "Steel", "project_id": project_id},
        headers=headers,
    )
    assert first.status_code == 200

    second = await async_client_full_schema.post(
        "/materials",
        json={"name": "Steel", "project_id": project_id},
        headers=headers,
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "Material name already exists"


@pytest.mark.anyio("asyncio")
async def test_delete_material_cascades_components(async_client_full_schema):
    login = await async_client_full_schema.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_resp = await async_client_full_schema.post(
        "/projects",
        json={"name": "Proj"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    mat_resp = await async_client_full_schema.post(
        "/materials",
        json={"name": "Steel", "project_id": project_id},
        headers=headers,
    )
    material_id = mat_resp.json()["id"]

    await async_client_full_schema.post(
        "/components",
        json={"name": "Comp", "material_id": material_id, "project_id": project_id},
        headers=headers,
    )

    # Delete using raw SQL to ensure DB-level cascading
    with backend.engine.begin() as conn:
        conn.execute(text("DELETE FROM materials WHERE id=:id"), {"id": material_id})

    resp = await async_client_full_schema.get(
        "/components",
        params={"project_id": project_id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []
