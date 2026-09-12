"""Strict provider-neutral contracts for confirmed retailer offers."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class McpContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommerceOffer(McpContract):
    offer_id: str = Field(min_length=1, max_length=160)
    candidate_id: str = Field(min_length=1, max_length=100)
    retailer_name: str = Field(min_length=1, max_length=200)
    product_name: str = Field(min_length=1, max_length=240)
    inventory_status: Literal["IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"]
    price: float = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    pickup_available: bool
    pickup_location: str | None = Field(default=None, max_length=240)
    product_url: str
    verified_at: datetime
    confidence: Literal["RECENTLY_OBSERVED"] = "RECENTLY_OBSERVED"


class CommerceLookupResult(McpContract):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    candidate_id: str
    zip_code: str = Field(pattern=r"^\d{5}$")
    offers: list[CommerceOffer] = Field(max_length=3)
    notice: Literal[
        "Inventory and price can change; confirm the offer with the retailer before purchase."
    ] = "Inventory and price can change; confirm the offer with the retailer before purchase."
