"""Run authenticated health and recommendation smoke tests from Google Cloud."""

import json
import os
import time
from urllib.parse import quote

import google.auth
import httpx
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token


def _self_signed_iap_jwt(service_account: str, api_url: str) -> str:
    credentials, _ = google.auth.default(scopes=("https://www.googleapis.com/auth/cloud-platform",))
    now = int(time.time())
    payload = json.dumps(
        {
            "iss": service_account,
            "sub": service_account,
            "aud": f"{api_url}/*",
            "iat": now,
            "exp": now + 600,
        },
        separators=(",", ":"),
    )
    signer = AuthorizedSession(credentials)
    response = signer.post(
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        f"{quote(service_account, safe='')}:signJwt",
        json={"payload": payload},
        timeout=30,
    )
    response.raise_for_status()
    signed_jwt = response.json().get("signedJwt")
    if not isinstance(signed_jwt, str) or not signed_jwt:
        raise RuntimeError("IAM Credentials did not return a signed JWT")
    return signed_jwt


def main() -> int:
    api_url = os.environ["API_URL"].rstrip("/")
    jwt_service_account = os.environ.get("IAP_JWT_SERVICE_ACCOUNT", "").strip()
    iap_client_id = os.environ.get("IAP_CLIENT_ID", "").strip()
    token = (
        _self_signed_iap_jwt(jwt_service_account, api_url)
        if jwt_service_account
        else id_token.fetch_id_token(Request(), iap_client_id or api_url)
    )
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
    cat_payload = {
        "category": "CAT",
        "destination": {"zip_code": "10001", "state_code": "NY"},
        "session_id": "f31a10c4-ec05-4ac4-b99a-4246d404e13e",
        "use_saved_preferences": False,
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
    }

    with httpx.Client(headers=headers, timeout=60) as client:
        live_response = client.get(f"{api_url}/health/live")
        ready_response = client.get(f"{api_url}/health/ready")
        recommendation_response = client.post(f"{api_url}/v1/recommendations", json=payload)
        cat_response = client.post(f"{api_url}/v1/recommendations", json=cat_payload)
        missing_plan_response = client.get(
            f"{api_url}/v1/care-plans/11111111-1111-4111-8111-111111111111"
        )
    live_response.raise_for_status()
    ready_response.raise_for_status()
    recommendation_response.raise_for_status()
    cat_response.raise_for_status()
    if missing_plan_response.status_code != 404:
        missing_plan_response.raise_for_status()

    live = live_response.json()
    ready = ready_response.json()
    recommendation = recommendation_response.json()
    cat_recommendation = cat_response.json()
    missing_plan_error = missing_plan_response.json()["error"]
    if cat_recommendation["category"] != "CAT" or not cat_recommendation["recommendations"]:
        raise RuntimeError("Cat recommendation smoke check failed")
    if (
        missing_plan_error["code"] != "RESOURCE_NOT_FOUND"
        or missing_plan_response.headers.get("X-Error-Contract-Version") != "v1"
    ):
        raise RuntimeError("Care Plan REST-to-MCP error contract smoke check failed")
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
        f" cat_recommendations={len(cat_recommendation['recommendations'])}"
        " care_plan_404=v1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
