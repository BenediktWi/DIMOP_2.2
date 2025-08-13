import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


pytest_plugins = ["tests.test_api"]


@pytest.mark.anyio("asyncio")
async def test_evaluation_endpoint(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post("/projects", json={"name": "Proj"}, headers=headers)
    project_id = proj.json()["id"]

    mat1 = await client.post(
        "/materials",
        json={
            "name": "Steel",
            "project_id": project_id,
            "total_gwp": 10.0,
            "fossil_gwp": 6.0,
            "biogenic_gwp": 4.0,
            "adpf": 2.0,
            "density": 4.0,
        },
        headers=headers,
    )
    mat1_id = mat1.json()["id"]

    mat2 = await client.post(
        "/materials",
        json={
            "name": "Wood",
            "project_id": project_id,
            "total_gwp": 5.0,
            "fossil_gwp": 2.0,
            "biogenic_gwp": 1.0,
            "adpf": 1.0,
            "density": 4.0,
        },
        headers=headers,
    )
    mat2_id = mat2.json()["id"]

    root = await client.post(
        "/components",
        json={
            "name": "Root",
            "material_id": mat1_id,
            "volume": 0.5,
            "project_id": project_id,
        },
        headers=headers,
    )
    root_id = root.json()["id"]

    child = await client.post(
        "/components",
        json={
            "name": "Child",
            "material_id": mat2_id,
            "parent_id": root_id,
            "volume": 0.25,
            "project_id": project_id,
        },
        headers=headers,
    )
    assert child.status_code == 200
    root_read = await client.get(
        f"/components/{root_id}",
        params={"project_id": project_id},
        headers=headers,
    )
    assert root_read.json()["weight"] == pytest.approx(2.0)
    child_read = await client.get(
        f"/components/{child.json()['id']}",
        params={"project_id": project_id},
        headers=headers,
    )
    assert child_read.json()["weight"] == pytest.approx(1.0)

    resp = await client.post(
        f"/evaluation/{root_id}",
        params={"project_id": project_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rv"] == pytest.approx(25.0)
    assert data["grade"] == "B"
    assert data["total_gwp"] == pytest.approx(25.0)
    assert data["fossil_gwp"] == pytest.approx(14.0)
    assert data["biogenic_gwp"] == pytest.approx(9.0)
    assert data["adpf"] == pytest.approx(5.0)
