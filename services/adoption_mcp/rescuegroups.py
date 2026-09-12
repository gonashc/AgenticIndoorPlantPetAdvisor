"""RescueGroups adapter hidden behind the adoption MCP contract."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

import httpx

PetCategory = Literal["DOG", "CAT"]


@dataclass(frozen=True, slots=True)
class AdoptionListing:
    name: str
    source_type: Literal["adoption_listing", "animal_rescue", "animal_shelter"]
    url: str
    distance_miles: float | None


class AdoptionProvider(Protocol):
    async def find_available_animals(
        self, *, category: PetCategory, zip_code: str, limit: int
    ) -> Sequence[AdoptionListing]: ...


class RescueGroupsClient:
    """Read-only client for public, currently available animal records."""

    _ANIMAL_FIELDS = "name,url,updatedDate,breedString"
    _ORG_FIELDS = "name,type,url,adoptionUrl"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        radius_miles: int,
        allowed_link_hosts: frozenset[str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._radius_miles = radius_miles
        self._allowed_link_hosts = allowed_link_hosts
        self._transport = transport

    async def find_available_animals(
        self, *, category: PetCategory, zip_code: str, limit: int
    ) -> Sequence[AdoptionListing]:
        species = "dogs" if category == "DOG" else "cats"
        url = f"{self._base_url}/public/animals/search/available/{species}/"
        params = {
            "limit": str(limit),
            "sort": "distance",
            "fields[animals]": self._ANIMAL_FIELDS,
            "fields[orgs]": self._ORG_FIELDS,
            "include": "orgs",
        }
        body = {
            "data": {
                "filterRadius": {
                    "postalcode": zip_code,
                    "miles": self._radius_miles,
                }
            }
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                url,
                params=params,
                headers={
                    "Authorization": self._api_key,
                    "Content-Type": "application/vnd.api+json",
                    "Accept": "application/vnd.api+json",
                },
                json=body,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"RescueGroups request failed with status {response.status_code}")
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("RescueGroups returned an invalid response")
        raw_animals = payload.get("data", [])
        if not isinstance(raw_animals, list):
            raise ValueError("RescueGroups response is missing the data list")
        organizations = self._organizations_by_id(payload.get("included", []))
        listings: list[AdoptionListing] = []
        for item in raw_animals:
            listing = self._parse_listing(item, organizations)
            if listing is not None:
                listings.append(listing)
            if len(listings) == limit:
                break
        return tuple(listings)

    def _parse_listing(
        self,
        item: Any,
        organizations: Mapping[str, Mapping[str, Any]],
    ) -> AdoptionListing | None:
        if not isinstance(item, Mapping):
            return None
        attributes = item.get("attributes")
        if not isinstance(attributes, Mapping):
            return None
        animal_name = attributes.get("name")
        if not isinstance(animal_name, str) or not animal_name.strip():
            return None
        organization = self._related_organization(item, organizations)
        org_attributes = organization.get("attributes", {}) if organization else {}
        if not isinstance(org_attributes, Mapping):
            org_attributes = {}
        url = self._safe_url(attributes.get("url"))
        if url is None:
            url = self._safe_url(org_attributes.get("adoptionUrl"))
        if url is None:
            url = self._safe_url(org_attributes.get("url"))
        if url is None:
            return None
        breed = attributes.get("breedString")
        org_name = org_attributes.get("name")
        details = [
            value.strip() for value in (breed, org_name) if isinstance(value, str) and value.strip()
        ]
        display_name = animal_name.strip()
        if details:
            display_name = f"{display_name} — {' · '.join(details)}"
        display_name = display_name[:200].rstrip()
        source_type = self._source_type(org_attributes.get("type"))
        return AdoptionListing(
            name=display_name,
            source_type=source_type,
            url=url,
            distance_miles=self._distance(item),
        )

    @staticmethod
    def _organizations_by_id(raw_included: Any) -> dict[str, Mapping[str, Any]]:
        if not isinstance(raw_included, list):
            return {}
        return {
            str(item["id"]): item
            for item in raw_included
            if isinstance(item, Mapping) and item.get("type") == "orgs" and "id" in item
        }

    @staticmethod
    def _related_organization(
        animal: Mapping[str, Any], organizations: Mapping[str, Mapping[str, Any]]
    ) -> Mapping[str, Any] | None:
        relationships = animal.get("relationships")
        if not isinstance(relationships, Mapping):
            return None
        org_relationship = relationships.get("orgs")
        if not isinstance(org_relationship, Mapping):
            return None
        raw_data = org_relationship.get("data")
        related = raw_data[0] if isinstance(raw_data, list) and raw_data else raw_data
        if not isinstance(related, Mapping) or related.get("type") != "orgs":
            return None
        identifier = related.get("id")
        return organizations.get(str(identifier)) if identifier is not None else None

    @staticmethod
    def _distance(animal: Mapping[str, Any]) -> float | None:
        meta = animal.get("meta")
        value = meta.get("distance") if isinstance(meta, Mapping) else None
        if not isinstance(value, (int, float, str)) or isinstance(value, bool):
            return None
        try:
            distance = float(value)
        except ValueError:
            return None
        return distance if distance >= 0 else None

    @staticmethod
    def _source_type(
        value: Any,
    ) -> Literal["adoption_listing", "animal_rescue", "animal_shelter"]:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if "shelter" in normalized:
                return "animal_shelter"
            if "rescue" in normalized:
                return "animal_rescue"
        return "adoption_listing"

    def _safe_url(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        parsed = urlparse(value.strip())
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if parsed.scheme != "https" or not any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in self._allowed_link_hosts
        ):
            return None
        return value.strip()
