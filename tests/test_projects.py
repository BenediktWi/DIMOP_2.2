import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # noqa: E402

import pytest

pytest_plugins = ["tests.test_api"]


@pytest.mark.anyio("asyncio")
async def test_create_project(async_client):
    login = await async_client.post(
        "/token",
        data={"username": "admin", "password": "secret"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await async_client.post(
        "/projects", json={"name": "Test"}, headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test"

    # database file should be created
    assert os.path.exists(f"project_{data['id']}.db")

    resp = await async_client.get("/projects", headers=headers)
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) == 1
    assert projects[0]["name"] == "Test"


