"""Google Places adapter hidden behind the plant-location MCP tool."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True, slots=True)
class PlaceListing:
    name: str
    maps_url: str


class PlantLocationProvider(Protocol):
    async def find_plant_nurseries(
        self, *, plant_name: str, zip_code: str, limit: int
    ) -> Sequence[PlaceListing]: ...


class GooglePlacesClient:
    _FIELD_MASK = "places.displayName,places.googleMapsUri"

    def __init__(
        self,
        *,
        api_key: str,
        url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = url
        self._timeout = timeout_seconds
        self._transport = transport

    async def find_plant_nurseries(
        self, *, plant_name: str, zip_code: str, limit: int
    ) -> Sequence[PlaceListing]:
        query = f"plant nurseries for {plant_name} near {zip_code}"
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                self._url,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": self._FIELD_MASK,
                },
                json={"textQuery": query, "pageSize": limit},
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Google Places request failed with status {response.status_code}")
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("Google Places returned an invalid response")
        raw_places = payload.get("places", [])
        if not isinstance(raw_places, list):
            raise ValueError("Google Places response is missing the places list")
        listings: list[PlaceListing] = []
        for item in raw_places[:limit]:
            listing = self._parse_listing(item)
            if listing is not None:
                listings.append(listing)
        return tuple(listings)

    @staticmethod
    def _parse_listing(item: Any) -> PlaceListing | None:
        if not isinstance(item, Mapping):
            return None
        display_name = item.get("displayName")
        maps_url = item.get("googleMapsUri")
        if not isinstance(display_name, Mapping) or not isinstance(maps_url, str):
            return None
        name = display_name.get("text")
        parsed = urlparse(maps_url)
        if not isinstance(name, str) or not name.strip():
            return None
        if parsed.scheme != "https" or parsed.hostname not in {
            "maps.google.com",
            "www.google.com",
            "goo.gl",
        }:
            return None
        return PlaceListing(name=name.strip(), maps_url=maps_url)
