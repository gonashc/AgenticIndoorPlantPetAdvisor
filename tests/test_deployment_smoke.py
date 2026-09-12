"""Deployment smoke-test authentication configuration."""

from scripts import smoke_deployed_api


def test_iap_client_id_is_used_as_token_audience(monkeypatch: object) -> None:
    calls: list[str] = []

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
    monkeypatch.setenv("IAP_CLIENT_ID", "iap-client.apps.googleusercontent.com")  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        smoke_deployed_api.id_token,
        "fetch_id_token",
        lambda _request, audience: calls.append(audience) or "token",
    )
    monkeypatch.setattr(smoke_deployed_api.httpx, "Client", FakeClient)  # type: ignore[attr-defined]

    assert smoke_deployed_api.main() == 0
    assert calls == ["iap-client.apps.googleusercontent.com"]
