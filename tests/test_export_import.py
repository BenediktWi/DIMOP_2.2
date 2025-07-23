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

pytest_plugins = ["tests.test_api"]


@pytest.mark.anyio("asyncio")
async def test_export_import_roundtrip(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await async_client.post(
        "/projects",
        json={"name": "Proj"},
        headers=headers,
    )
    project_id = proj.json()["id"]

    resp = await async_client.post(
        "/materials",
        json={"name": "Steel", "project_id": project_id},
        headers=headers,
    )
    material_id = resp.json()["id"]

    await async_client.post(
        "/components",
        json={"name": "Root", "material_id": material_id, "project_id": project_id},
        headers=headers,
    )

    resp = await async_client.get(
        "/export",
        params={"project_id": project_id},
        headers=headers,
    )
    assert resp.status_code == 200
    csv_data = resp.text

    engine2 = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine2.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE materials (id INTEGER PRIMARY KEY, name VARCHAR, description VARCHAR)"
            )
        )
    TestingSessionLocal = sessionmaker(
        bind=engine2, autoflush=False, autocommit=False
    )
    backend.engine = engine2
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
        login2 = await ac.post(
            "/token",
            data={"username": "admin", "password": "secret"},
        )
        token2 = login2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}
        files = {"file": ("data.csv", csv_data, "text/csv")}
        resp = await ac.post("/import", files=files, headers=headers2)
        assert resp.status_code == 200

        resp = await ac.get(
            "/materials",
            params={"project_id": project_id},
            headers=headers2,
        )
        assert len(resp.json()) == 1
        resp = await ac.get(
            "/components",
            params={"project_id": project_id},
            headers=headers2,
        )
        assert len(resp.json()) == 1

    backend.app.dependency_overrides.clear()
