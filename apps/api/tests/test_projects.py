from tests.conftest import published_agent


async def test_project_can_be_deleted_even_when_planning_never_started(alice):
    agent = await published_agent(alice)
    created = await alice.post("/projects", json={
        "name": "Project to remove",
        "idea": "Build a small example application for testing project deletion",
        "planning_agent_ids": [agent["id"]],
    })
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    deleted = await alice.delete(f"/projects/{project_id}")
    assert deleted.status_code == 204, deleted.text
    assert all(p["id"] != project_id for p in (await alice.get("/projects")).json()["items"])
    assert (await alice.get(f"/projects/{project_id}")).status_code == 404
