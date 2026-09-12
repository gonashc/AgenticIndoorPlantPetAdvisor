"""Deployment smoke-test authentication configuration."""

from scripts import smoke_deployed_api


def test_self_signed_jwt_is_used_for_iap_smoke(monkeypatch: object) -> None:
    calls: list[tuple[str, str]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"status": "ok"}

    class FakeClient:
        def __init__(self, **_: object) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, _: str) -> FakeResponse:
            return FakeResponse()

        def post(self, _: str, **__: object) -> FakeResponse:
            response = FakeResponse()
            response.json = lambda: {
                "category": "PLANT",
                "recommendations": [],
                "metadata": {"versions": {"knowledge": "test"}},
                "warnings": [],
            }
            return response

    monkeypatch.setenv("API_URL", "https://api.example")  # type: ignore[attr-defined]
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "IAP_JWT_SERVICE_ACCOUNT", "advisor-api@example.iam.gserviceaccount.com"
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        smoke_deployed_api,
        "_self_signed_iap_jwt",
        lambda service_account, api_url: calls.append((service_account, api_url)) or "token",
    )
    monkeypatch.setattr(smoke_deployed_api.httpx, "Client", FakeClient)  # type: ignore[attr-defined]

    assert smoke_deployed_api.main() == 0
    assert calls == [("advisor-api@example.iam.gserviceaccount.com", "https://api.example")]
