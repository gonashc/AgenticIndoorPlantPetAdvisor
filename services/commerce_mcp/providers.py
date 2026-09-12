"""Provider port for confirmed inventory, price, and pickup availability."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

InventoryStatus = Literal["IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"]


@dataclass(frozen=True, slots=True)
class RetailOffer:
    offer_id: str
    candidate_id: str
    retailer_name: str
    product_name: str
    inventory_status: InventoryStatus
    price: float
    currency: str
    pickup_available: bool
    pickup_location: str | None
    product_url: str


@dataclass(frozen=True, slots=True)
class CommerceProviderResult:
    available: bool
    offers: Sequence[RetailOffer]


class CommerceProvider(Protocol):
    async def find_offers(
        self,
        *,
        category: Literal["PLANT", "DOG", "CAT"],
        candidate_id: str,
        zip_code: str,
        limit: int,
    ) -> CommerceProviderResult: ...


class DisabledCommerceProvider:
    """Safe fallback used until a retailer contract and adapter are configured."""

    async def find_offers(
        self,
        *,
        category: Literal["PLANT", "DOG", "CAT"],
        candidate_id: str,
        zip_code: str,
        limit: int,
    ) -> CommerceProviderResult:
        del category, candidate_id, zip_code, limit
        return CommerceProviderResult(available=False, offers=())
