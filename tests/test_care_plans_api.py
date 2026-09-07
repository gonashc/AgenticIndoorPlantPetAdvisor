"""Care-plan confirmation and lifecycle tests."""

from fastapi.testclient import TestClient


def _preview(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/v1/care-plans/preview",
        json={
            "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
            "recommendation_id": "plant-spider",
            "category": "PLANT",
            "item_name": "Spider Plant",
            "start_date": "2026-09-05",
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_care_plan_requires_preview_and_literal_confirmation(client: TestClient) -> None:
    preview = _preview(client)
    rejected = client.post(
        "/v1/care-plans",
        json={"preview_id": preview["preview_id"], "confirmed": False},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"

    created = client.post(
        "/v1/care-plans",
        json={"preview_id": preview["preview_id"], "confirmed": True},
    )
    assert created.status_code == 201
    plan = created.json()
    assert plan["status"] == "ACTIVE"
    assert plan["version"] == 1
    assert len(plan["tasks"]) == 3

    fetched = client.get(f"/v1/care-plans/{plan['plan_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == plan["plan_id"]

    task_id = plan["tasks"][0]["task_id"]
    completed = client.post(f"/v1/care-plans/{plan['plan_id']}/tasks/{task_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["tasks"][0]["completed_at"] is not None
    assert completed.json()["version"] == 2

    paused = client.patch(f"/v1/care-plans/{plan['plan_id']}", json={"status": "PAUSED"})
    assert paused.status_code == 200
    assert paused.json()["version"] == 3
    conflict = client.post(
        f"/v1/care-plans/{plan['plan_id']}/tasks/{plan['tasks'][1]['task_id']}/complete"
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CARE_PLAN_PAUSED"

    duplicate = client.post(
        "/v1/care-plans",
        json={"preview_id": preview["preview_id"], "confirmed": True},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CARE_PLAN_PREVIEW_ALREADY_CONSUMED"


def test_missing_care_plan_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/v1/care-plans/11111111-1111-4111-8111-111111111111")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
