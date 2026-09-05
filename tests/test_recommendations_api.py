"""Recommendation contract and safety integration tests."""

import json

from fastapi.testclient import TestClient


def _dog_exclusion_payload() -> dict[str, object]:
    return {
        "category": "DOG",
        "destination": {"zip_code": "30301", "state_code": "GA"},
        "session_id": "7649ff84-05a3-4509-9ae5-62dfaf05d952",
        "questionnaire": {
            "housing_type": "APARTMENT",
            "home_size": "SMALL",
            "rental_allows_pets": False,
            "outdoor_space": "NONE",
            "hours_alone": 4,
            "activity_level": "LOW",
            "grooming_tolerance": "LOW",
            "monthly_budget": 200,
            "children_present": False,
            "existing_pets": [],
            "experience": "BEGINNER",
        },
    }


def test_plant_recommendations_exclude_toxic_candidates(
    client: TestClient, plant_payload: dict[str, object]
) -> None:
    response = client.post("/v1/recommendations", json=plant_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "PLANT"
    assert 1 <= len(body["recommendations"]) <= 3
    assert "plant-pothos" not in {item["recommendation_id"] for item in body["recommendations"]}
    assert all(len(item["reasons"]) >= 3 for item in body["recommendations"])
    assert all(item["score"] >= 0 for item in body["recommendations"])
    assert all(item["safety"]["cat_toxicity"] == "NON_TOXIC" for item in body["recommendations"])
    assert all(
        item["safety"]["hard_constraints_passed"] is True for item in body["recommendations"]
    )
    assert body["validation_status"] == "DEGRADED"
    assert response.headers["X-API-Version"] == "v1"
    assert response.headers["X-Request-ID"] == body["metadata"]["request_id"]


def test_category_discriminator_rejects_wrong_questionnaire(
    client: TestClient, plant_payload: dict[str, object]
) -> None:
    plant_payload["category"] = "DOG"
    response = client.post("/v1/recommendations", json=plant_payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "REQUEST_VALIDATION_FAILED"
    assert error["contract_version"] == "v1"
    assert error["details"]


def test_pet_housing_hard_constraint_can_reject_all_candidates(client: TestClient) -> None:
    response = client.post("/v1/recommendations", json=_dog_exclusion_payload())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_CANDIDATES"


def test_recommendation_stream_uses_sse_contract(
    client: TestClient, plant_payload: dict[str, object]
) -> None:
    with client.stream("POST", "/v1/recommendations/stream", json=plant_payload) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    blocks = [block for block in body.split("\n\n") if block]
    events = []
    for block in blocks:
        data_line = next(line for line in block.splitlines() if line.startswith("data: "))
        events.append(json.loads(data_line.removeprefix("data: ")))
    assert events[0]["event"] == "progress"
    assert events[0]["data"]["stage"] == "ACCEPTED"
    assert events[-1]["event"] == "completed"
    assert events[-1]["data"]["category"] == "PLANT"
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)


def test_stream_reports_domain_failure_as_terminal_event(client: TestClient) -> None:
    with client.stream(
        "POST", "/v1/recommendations/stream", json=_dog_exclusion_payload()
    ) as response:
        body = "".join(response.iter_text())

    data_lines = [
        line.removeprefix("data: ") for line in body.splitlines() if line.startswith("data: ")
    ]
    events = [json.loads(line) for line in data_lines]
    assert response.status_code == 200
    assert events[-1]["event"] == "failed"
    assert events[-1]["data"]["code"] == "NO_ELIGIBLE_CANDIDATES"


def test_stream_can_filter_already_seen_sequences(
    client: TestClient, plant_payload: dict[str, object]
) -> None:
    response = client.post(
        "/v1/recommendations/stream",
        json=plant_payload,
        headers={"Last-Event-ID": "previous-request:2"},
    )
    first_data = next(
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    )

    assert json.loads(first_data)["sequence"] == 3


def test_cat_category_uses_profile_results(client: TestClient) -> None:
    response = client.post(
        "/v1/recommendations",
        json={
            "category": "CAT",
            "destination": {"zip_code": "98101", "state_code": "WA"},
            "session_id": "a3233020-9f22-4fe7-b22f-7fe9f438fd80",
            "questionnaire": {
                "housing_type": "APARTMENT",
                "home_size": "SMALL",
                "rental_allows_pets": True,
                "outdoor_space": "NONE",
                "hours_alone": 7,
                "activity_level": "MEDIUM",
                "grooming_tolerance": "LOW",
                "monthly_budget": 220,
                "children_present": False,
                "existing_pets": [],
                "experience": "BEGINNER",
                "affection_preference": "BALANCED",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["category"] == "CAT"
    assert all(
        item["safety"]["cat_toxicity"] == "NOT_APPLICABLE"
        for item in response.json()["recommendations"]
    )
