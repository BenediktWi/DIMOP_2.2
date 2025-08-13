import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


pytest_plugins = ["tests.test_api"]


@pytest.mark.anyio("asyncio")
async def test_recycle_evaluation(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post(
        "/projects",
        json={"name": "Proj", "r_strategies": ["R8"]},
        headers=headers,
    )
    project_id = proj.json()["id"]

    mat1 = await client.post(
        "/materials",
        json={
            "name": "Mat1",
            "project_id": project_id,
            "density": 1.0,
        },
        headers=headers,
    )
    mat2 = await client.post(
        "/materials",
        json={
            "name": "Mat2",
            "project_id": project_id,
            "density": 1.0,
        },
        headers=headers,
    )
    mat1_id = mat1.json()["id"]
    mat2_id = mat2.json()["id"]

    root = await client.post(
        "/components",
        json={
            "name": "Root",
            "project_id": project_id,
            "material_id": mat1_id,
            "level": 0,
            "volume": 2.0,
            "systemability": 1.0,
            "r_factor": 1.0,
            "trenn_eff": 1.0,
            "sort_eff": 1.0,
            "mv_bonus": 0.0,
            "mv_abzug": 0.0,
        },
        headers=headers,
    )
    root_id = root.json()["id"]

    await client.post(
        "/components",
        json={
            "name": "Child",
            "project_id": project_id,
            "material_id": mat2_id,
            "parent_id": root_id,
            "level": 1,
            "volume": 1.0,
            "r_factor": 0.9,
            "trenn_eff": 0.95,
            "sort_eff": 0.95,
        },
        headers=headers,
    )

    resp = await client.post(
        f"/recycle/{project_id}", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recycle_value"] == pytest.approx(0.935, rel=1e-2)
    assert data["grade"] == "B"
