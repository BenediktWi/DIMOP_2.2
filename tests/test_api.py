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
                "CREATE TABLE components (id INTEGER PRIMARY KEY, name VARCHAR, material_id INTEGER, density FLOAT)"
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
async def test_update_component_material_no_project_id(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await async_client.post(
        "/projects", json={"name": "Proj"}, headers=headers
    )
    project_id = proj.json()["id"]

    mat1 = await async_client.post(
        "/materials",
        json={"name": "Old", "project_id": project_id},
        headers=headers,
    )
    mat2 = await async_client.post(
        "/materials",
        json={"name": "New", "project_id": project_id, "density": 2.5},
        headers=headers,
    )
    mat2_id = mat2.json()["id"]

    comp = await async_client.post(
        "/components",
        json={
            "name": "Comp",
            "material_id": mat1.json()["id"],
            "volume": 3.0,
            "project_id": project_id,
            "is_atomic": True,
        },
        headers=headers,
    )
    comp_id = comp.json()["id"]
    assert comp.json()["weight"] == 0.0

    resp = await async_client.put(
        f"/components/{comp_id}",
        json={"material_id": mat2_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["material_id"] == mat2_id
    assert data["weight"] == pytest.approx(7.5)


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
            "is_atomic": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data

    inspector = backend.inspect(backend.engine)
    cols = [c["name"] for c in inspector.get_columns("components")]
    assert "level" in cols
    assert "weight" in cols
    assert "density" not in cols

    mat_cols = [c["name"] for c in inspector.get_columns("materials")]
    assert "total_gwp" in mat_cols
    assert "fossil_gwp" in mat_cols
    assert "biogenic_gwp" in mat_cols
    assert "adpf" in mat_cols
    assert "density" in mat_cols
    assert "is_dangerous" in mat_cols
    
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
        json={
            "name": "Comp",
            "material_id": material_id,
            "project_id": project_id,
            "is_atomic": True,
        },
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


@pytest.mark.anyio("asyncio")
async def test_recursive_weight_calculation(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await async_client.post(
        "/projects", json={"name": "Proj"}, headers=headers
    )
    project_id = proj.json()["id"]

    m1 = await async_client.post(
        "/materials",
        json={"name": "M1", "density": 1.5, "project_id": project_id},
        headers=headers,
    )
    m2 = await async_client.post(
        "/materials",
        json={"name": "M2", "density": 2.0, "project_id": project_id},
        headers=headers,
    )
    m3 = await async_client.post(
        "/materials",
        json={"name": "M3", "density": 10.0, "project_id": project_id},
        headers=headers,
    )
    m4 = await async_client.post(
        "/materials",
        json={"name": "M4", "density": 2.0, "project_id": project_id},
        headers=headers,
    )
    m5 = await async_client.post(
        "/materials",
        json={"name": "M5", "density": 3.0, "project_id": project_id},
        headers=headers,
    )

    A = await async_client.post(
        "/components",
        json={"name": "A", "project_id": project_id, "is_atomic": False},
        headers=headers,
    )
    A_id = A.json()["id"]
    B = await async_client.post(
        "/components",
        json={
            "name": "B",
            "project_id": project_id,
            "is_atomic": True,
            "volume": 2,
            "material_id": m1.json()["id"],
            "parent_id": A_id,
        },
        headers=headers,
    )
    C = await async_client.post(
        "/components",
        json={
            "name": "C",
            "project_id": project_id,
            "is_atomic": True,
            "volume": 3,
            "material_id": m2.json()["id"],
            "parent_id": A_id,
        },
        headers=headers,
    )
    assert B.json()["weight"] == pytest.approx(3.0)
    assert C.json()["weight"] == pytest.approx(6.0)
    A_read = await async_client.get(
        f"/components/{A_id}",
        params={"project_id": project_id},
        headers=headers,
    )
    assert A_read.json()["weight"] == pytest.approx(9.0)

    D = await async_client.post(
        "/components",
        json={"name": "D", "project_id": project_id, "is_atomic": False},
        headers=headers,
    )
    D_id = D.json()["id"]
    E = await async_client.post(
        "/components",
        json={
            "name": "E",
            "project_id": project_id,
            "is_atomic": False,
            "parent_id": D_id,
        },
        headers=headers,
    )
    E_id = E.json()["id"]
    F = await async_client.post(
        "/components",
        json={
            "name": "F",
            "project_id": project_id,
            "is_atomic": True,
            "volume": 1,
            "material_id": m3.json()["id"],
            "parent_id": D_id,
        },
        headers=headers,
    )
    G = await async_client.post(
        "/components",
        json={
            "name": "G",
            "project_id": project_id,
            "is_atomic": True,
            "volume": 2,
            "material_id": m4.json()["id"],
            "parent_id": E_id,
        },
        headers=headers,
    )
    H = await async_client.post(
        "/components",
        json={
            "name": "H",
            "project_id": project_id,
            "is_atomic": True,
            "volume": 1,
            "material_id": m5.json()["id"],
            "parent_id": E_id,
        },
        headers=headers,
    )
    assert G.json()["weight"] == pytest.approx(4.0)
    assert H.json()["weight"] == pytest.approx(3.0)
    E_read = await async_client.get(
        f"/components/{E_id}",
        params={"project_id": project_id},
        headers=headers,
    )
    F_read = await async_client.get(
        f"/components/{F.json()['id']}",
        params={"project_id": project_id},
        headers=headers,
    )
    D_read = await async_client.get(
        f"/components/{D_id}",
        params={"project_id": project_id},
        headers=headers,
    )
    assert E_read.json()["weight"] == pytest.approx(7.0)
    assert F_read.json()["weight"] == pytest.approx(10.0)
    assert D_read.json()["weight"] == pytest.approx(17.0)

