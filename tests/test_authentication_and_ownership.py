"""Authentication envelope and cross-owner isolation tests."""

from uuid import UUID

import pytest
from advisor_api import create_app
from advisor_api.adapters.auth import GoogleIapTokenVerifier
from advisor_api.config import Settings
from advisor_api.http.errors import AuthenticationError
from advisor_api.ports.auth import AuthenticatedUser
from fastapi.testclient import TestClient


class HeaderIdentityVerifier:
    async def verify(self, token: str | None) -> AuthenticatedUser:
        if token not in {"owner-a", "owner-b"}:
            raise AuthenticationError()
        owner_id = {
            "owner-a": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            "owner-b": UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        }[token]
        return AuthenticatedUser(owner_id=owner_id, subject=token, issuer="test-issuer")


@pytest.mark.asyncio
async def test_iap_verifier_derives_stable_owner_without_retaining_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = GoogleIapTokenVerifier("/projects/123/locations/us-east1/services/advisor-api")
    monkeypatch.setattr(
        verifier,
        "_verify",
        lambda token: {
            "sub": "accounts.google.com:123456789",
            "iss": "https://cloud.google.com/iap",
            "email": "private@example.com",
        },
    )

    first = await verifier.verify("signed-token")
    second = await verifier.verify("signed-token")

    assert first.owner_id == second.owner_id
    assert first.subject == "accounts.google.com:123456789"
    assert not hasattr(first, "email")


def _authenticated_client() -> TestClient:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            auth_mode="google_iap",
            iap_audience="/projects/123/locations/us-east1/services/advisor-api",
            enabled_categories="PLANT,DOG",
        )
    )
    app.state.identity_token_verifier = HeaderIdentityVerifier()
    return TestClient(app, raise_server_exceptions=False)


def _preview(client: TestClient, owner: str) -> dict[str, object]:
    response = client.post(
        "/v1/care-plans/preview",
        headers={"X-Goog-IAP-JWT-Assertion": owner},
        json={
            "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
            "recommendation_id": "plant-spider",
            "category": "PLANT",
            "item_name": "Spider Plant",
            "start_date": "2026-09-11",
            "timezone": "America/New_York",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_missing_identity_uses_versioned_error_envelope() -> None:
    with _authenticated_client() as client:
        response = client.get("/v1/care-plans/11111111-1111-4111-8111-111111111111")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["x-error-contract-version"] == "v1"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_care_plan_preview_and_plan_are_isolated_by_owner() -> None:
    with _authenticated_client() as client:
        preview = _preview(client, "owner-a")
        other_owner_confirmation = client.post(
            "/v1/care-plans",
            headers={"X-Goog-IAP-JWT-Assertion": "owner-b"},
            json={"preview_id": preview["preview_id"], "confirmed": True},
        )
        assert other_owner_confirmation.status_code == 404

        created = client.post(
            "/v1/care-plans",
            headers={"X-Goog-IAP-JWT-Assertion": "owner-a"},
            json={"preview_id": preview["preview_id"], "confirmed": True},
        )
        assert created.status_code == 201

        hidden = client.get(
            f"/v1/care-plans/{created.json()['plan_id']}",
            headers={"X-Goog-IAP-JWT-Assertion": "owner-b"},
        )
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_cat_is_closed_until_reviewed_content_is_available() -> None:
    with _authenticated_client() as client:
        response = client.post(
            "/v1/recommendations",
            headers={"X-Goog-IAP-JWT-Assertion": "owner-a"},
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

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CATEGORY_NOT_AVAILABLE"
