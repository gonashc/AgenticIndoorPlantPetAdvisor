"""Deployment smoke-test authentication configuration."""

from scripts import smoke_deployed_api


def test_self_signed_jwt_is_used_for_iap_smoke(monkeypatch: object) -> None:
    calls: list[tuple[str, str]] = []

    class FakeResponse:
        def __init__(
            self,
            payload: dict[str, object] | None = None,
            *,
            status_code: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            self._payload = payload or {"status": "ok"}
            self.status_code = status_code
            self.headers = headers or {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, **_: object) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, url: str) -> FakeResponse:
            if "/v1/care-plans/" in url:
                return FakeResponse(
                    {"error": {"code": "RESOURCE_NOT_FOUND"}},
                    status_code=404,
                    headers={"X-Error-Contract-Version": "v1"},
                )
            return FakeResponse()

        def post(self, _: str, **kwargs: object) -> FakeResponse:
            payload = kwargs["json"]
            assert isinstance(payload, dict)
            category = payload["category"]
            return FakeResponse(
                {
                    "category": category,
                    "recommendations": [{}] if category == "CAT" else [],
                    "metadata": {"versions": {"knowledge": "test"}},
                    "warnings": [],
                }
            )

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
