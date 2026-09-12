"""Bounded U.S. ZIP-to-coordinate provider for climate lookups."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

_ZIP_CODE = re.compile(r"^\d{5}$")


@dataclass(frozen=True, slots=True)
class ResolvedZip:
    zip_code: str
    latitude: float
    longitude: float
    city: str | None
    state_code: str


class ZipCoordinateProvider(Protocol):
    async def resolve(self, zip_code: str) -> ResolvedZip: ...


class GoogleZipCoordinateClient:
    """Calls only Google's component-filtered U.S. postal-code geocoder."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Google geocoding API key is required")
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._transport = transport

    async def resolve(self, zip_code: str) -> ResolvedZip:
        if not _ZIP_CODE.fullmatch(zip_code):
            raise ValueError("zip_code must contain exactly five digits")
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(
                self._base_url,
                params={
                    "components": f"postal_code:{zip_code}|country:US",
                    "key": self._api_key,
                },
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Geocoding request failed with status {response.status_code}")
        payload = response.json()
        if not isinstance(payload, Mapping) or payload.get("status") != "OK":
            raise ValueError("ZIP code could not be resolved")
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError("ZIP code could not be resolved")
        result = results[0]
        if not isinstance(result, Mapping) or result.get("partial_match") is True:
            raise ValueError("ZIP geocoder returned a partial match")
        components = self._components(result)
        if components.get("postal_code") != zip_code or components.get("country") != "US":
            raise ValueError("ZIP geocoder returned a mismatched postal area")
        state_code = components.get("administrative_area_level_1")
        if state_code is None or not re.fullmatch(r"[A-Z]{2}", state_code):
            raise ValueError("ZIP geocoder did not return a U.S. state")
        latitude, longitude = self._coordinates(result)
        return ResolvedZip(
            zip_code=zip_code,
            latitude=latitude,
            longitude=longitude,
            city=components.get("locality") or components.get("postal_town"),
            state_code=state_code,
        )

    @staticmethod
    def _components(result: Mapping[str, Any]) -> dict[str, str]:
        raw = result.get("address_components")
        if not isinstance(raw, list):
            raise ValueError("ZIP geocoder response is missing address components")
        values: dict[str, str] = {}
        for component in raw:
            if not isinstance(component, Mapping):
                continue
            short_name = component.get("short_name")
            types = component.get("types")
            if not isinstance(short_name, str) or not isinstance(types, list):
                continue
            for component_type in types:
                if isinstance(component_type, str):
                    values[component_type] = short_name.strip()
        return values

    @staticmethod
    def _coordinates(result: Mapping[str, Any]) -> tuple[float, float]:
        geometry = result.get("geometry")
        if not isinstance(geometry, Mapping):
            raise ValueError("ZIP geocoder response is missing geometry")
        location = geometry.get("location")
        if not isinstance(location, Mapping):
            raise ValueError("ZIP geocoder response is missing location")
        latitude = location.get("lat")
        longitude = location.get("lng")
        if (
            not isinstance(latitude, (int, float))
            or isinstance(latitude, bool)
            or not isinstance(longitude, (int, float))
            or isinstance(longitude, bool)
            or not -90 <= float(latitude) <= 90
            or not -180 <= float(longitude) <= 180
        ):
            raise ValueError("ZIP geocoder returned invalid coordinates")
        return float(latitude), float(longitude)
