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
    headers = {"Authorization": f"Bearer {token}", "X-Project": "1"}

    resp = await async_client.post(
        "/materials",
        json={"name": "Steel"},
        headers=headers,
    )
    material_id = resp.json()["id"]

    await async_client.post(
        "/components",
        json={"name": "Root", "material_id": material_id},
        headers=headers,
    )

    resp = await async_client.get("/export", headers=headers)
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
    backend.PROJECT_DATABASES = {"1": TestingSessionLocal}
    backend.on_startup()
    transport = ASGITransport(app=backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        login2 = await ac.post(
            "/token",
            data={"username": "admin", "password": "secret"},
        )
        token2 = login2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}", "X-Project": "1"}
        files = {"file": ("data.csv", csv_data, "text/csv")}
        resp = await ac.post("/import", files=files, headers=headers2)
        assert resp.status_code == 200

        resp = await ac.get("/materials", headers=headers2)
        assert len(resp.json()) == 1
        resp = await ac.get("/components", headers=headers2)
        assert len(resp.json()) == 1

    backend.PROJECT_DATABASES = {}
