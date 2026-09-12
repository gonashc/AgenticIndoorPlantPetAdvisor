"""Run authenticated health and recommendation smoke tests from Google Cloud."""

import os

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def main() -> int:
    api_url = os.environ["API_URL"].rstrip("/")
    token = id_token.fetch_id_token(Request(), api_url)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "category": "PLANT",
        "destination": {"zip_code": "10001", "state_code": "NY"},
        "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
        "use_saved_preferences": False,
        "questionnaire": {
            "light_level": "BRIGHT_INDIRECT",
            "humidity": "AVERAGE",
            "indoor_temperature_f": 72,
            "available_space": "MEDIUM",
            "experience": "BEGINNER",
            "watering_availability": "LOW",
            "monthly_budget": 30,
            "children_present": True,
            "pets_present": ["CAT"],
        },
    }

    with httpx.Client(headers=headers, timeout=60) as client:
        live_response = client.get(f"{api_url}/health/live")
        ready_response = client.get(f"{api_url}/health/ready")
        recommendation_response = client.post(f"{api_url}/v1/recommendations", json=payload)
    live_response.raise_for_status()
    ready_response.raise_for_status()
    recommendation_response.raise_for_status()

    live = live_response.json()
    ready = ready_response.json()
    recommendation = recommendation_response.json()
    evidence_ids = [
        evidence["evidence_id"]
        for item in recommendation["recommendations"]
        for evidence in item["evidence"]
    ]
    retrieved_chunks = sum(
        1
        for evidence_id in evidence_ids
        if len(evidence_id) == 40
        and all(character in "0123456789abcdef" for character in evidence_id)
    )
    print(
        f"live={live['status']} ready={ready['status']} "
        f"category={recommendation['category']} "
        f"recommendations={len(recommendation['recommendations'])} "
        f"knowledge={recommendation['metadata']['versions']['knowledge']} "
        f"retrieved_chunks={retrieved_chunks} "
        f"warnings={len(recommendation['warnings'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
