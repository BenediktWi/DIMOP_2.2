import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

pytest_plugins = ["tests.test_api"]


async def _setup(client, headers, *, systemability=1.0, dangerous=False, mv_abzug2=0.0):
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
            "is_dangerous": False,
        },
        headers=headers,
    )
    mat2 = await client.post(
        "/materials",
        json={
            "name": "Mat2",
            "project_id": project_id,
            "density": 1.0,
            "is_dangerous": dangerous,
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
            "systemability": systemability,
        },
        headers=headers,
    )
    root_id = root.json()["id"]

    await client.post(
        "/components",
        json={
            "name": "Atom1",
            "project_id": project_id,
            "material_id": mat1_id,
            "parent_id": root_id,
            "level": 1,
            "is_atomic": True,
            "volume": 1.0,
            "r_factor": 1.0,
            "trenn_eff": 1.0,
            "sort_eff": 1.0,
            "mv_bonus": 0.5,
            "mv_abzug": 0.0,
        },
        headers=headers,
    )
    await client.post(
        "/components",
        json={
            "name": "Atom2",
            "project_id": project_id,
            "material_id": mat2_id,
            "parent_id": root_id,
            "level": 1,
            "is_atomic": True,
            "volume": 1.0,
            "r_factor": 0.9,
            "trenn_eff": 0.95,
            "sort_eff": 0.9,
            "mv_bonus": 0.5,
            "mv_abzug": mv_abzug2,
        },
        headers=headers,
    )
    return project_id


@pytest.mark.anyio("asyncio")
async def test_recycle_evaluation_basic(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    project_id = await _setup(client, headers)

    resp = await client.post(f"/recycle/{project_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recycle_value"] == pytest.approx(0.999, rel=1e-3)
    assert data["grade"] == "A"


@pytest.mark.anyio("asyncio")
async def test_recycle_systemability_gate(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    project_id = await _setup(client, headers, systemability=0.0)

    resp = await client.post(f"/recycle/{project_id}", headers=headers)
    data = resp.json()
    assert data == {"recycle_value": 0.0, "grade": "F"}


@pytest.mark.anyio("asyncio")
async def test_recycle_dangerous_material_gate(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    project_id = await _setup(client, headers, dangerous=True)

    resp = await client.post(f"/recycle/{project_id}", headers=headers)
    data = resp.json()
    assert data == {"recycle_value": 0.0, "grade": "F"}


@pytest.mark.anyio("asyncio")
async def test_recycle_non_atomic_dangerous_ok(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = await client.post(
        "/projects",
        json={"name": "Proj2", "r_strategies": ["R8"]},
        headers=headers,
    )
    project_id = proj.json()["id"]

    root_mat = await client.post(
        "/materials",
        json={
            "name": "RootMat",
            "project_id": project_id,
            "density": 1.0,
            "is_dangerous": True,
        },
        headers=headers,
    )
    root_mat_id = root_mat.json()["id"]

    mat1 = await client.post(
        "/materials",
        json={
            "name": "Safe1",
            "project_id": project_id,
            "density": 1.0,
            "is_dangerous": False,
        },
        headers=headers,
    )
    mat2 = await client.post(
        "/materials",
        json={
            "name": "Safe2",
            "project_id": project_id,
            "density": 1.0,
            "is_dangerous": False,
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
            "material_id": root_mat_id,
            "level": 0,
            "systemability": 1.0,
        },
        headers=headers,
    )
    root_id = root.json()["id"]

    for comp in [
        {
            "name": "Atom1",
            "project_id": project_id,
            "material_id": mat1_id,
            "parent_id": root_id,
            "level": 1,
            "is_atomic": True,
            "volume": 1.0,
            "r_factor": 1.0,
            "trenn_eff": 1.0,
            "sort_eff": 1.0,
            "mv_bonus": 0.5,
            "mv_abzug": 0.0,
        },
        {
            "name": "Atom2",
            "project_id": project_id,
            "material_id": mat2_id,
            "parent_id": root_id,
            "level": 1,
            "is_atomic": True,
            "volume": 1.0,
            "r_factor": 0.9,
            "trenn_eff": 0.95,
            "sort_eff": 0.9,
            "mv_bonus": 0.5,
            "mv_abzug": 0.0,
        },
    ]:
        await client.post("/components", json=comp, headers=headers)

    resp = await client.post(f"/recycle/{project_id}", headers=headers)
    data = resp.json()
    assert data["grade"] == "A"


@pytest.mark.anyio("asyncio")
async def test_recycle_contamination_gate(async_client_full_schema):
    client = async_client_full_schema
    login = await client.post(
        "/token", data={"username": "admin", "password": "secret"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    project_id = await _setup(client, headers, mv_abzug2=3)

    resp = await client.post(f"/recycle/{project_id}", headers=headers)
    data = resp.json()
    assert data == {"recycle_value": 0.0, "grade": "F"}
