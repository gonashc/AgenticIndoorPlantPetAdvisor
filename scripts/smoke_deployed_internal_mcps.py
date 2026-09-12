"""Run non-mutating smoke checks against deployed private internal MCP services."""

import argparse
import asyncio
import os
from collections.abc import Mapping
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def call_tool(
    base_url: str,
    token: str,
    tool_name: str,
    arguments: Mapping[str, object],
) -> Any:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(20),
    ) as http_client:
        transport = streamable_http_client(f"{base_url}/mcp", http_client=http_client)
        async with Client(transport, read_timeout_seconds=20) as client:
            return await client.call_tool(tool_name, dict(arguments), read_timeout_seconds=20)


async def run(arguments: argparse.Namespace) -> None:
    token = os.environ.get("MCP_VERIFY_ID_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MCP_VERIFY_ID_TOKEN is required")

    catalog = await call_tool(
        arguments.catalog_url,
        token,
        "get_profiles",
        {"category": "PLANT", "candidate_ids": ["plant-spider"]},
    )
    if catalog.is_error or not catalog.structured_content:
        raise RuntimeError("Catalog MCP smoke call failed")
    profiles = catalog.structured_content.get("profiles", [])
    if not profiles or profiles[0].get("candidate_id") != "plant-spider":
        raise RuntimeError("Catalog MCP returned an unexpected profile")

    regulations = await call_tool(
        arguments.regulations_url,
        token,
        "lookup_pet_regulations",
        {"category": "DOG", "state_code": "NY", "city": "New York"},
    )
    if regulations.is_error or not regulations.structured_content:
        raise RuntimeError("Regulations MCP smoke call failed")
    if regulations.structured_content.get("status") != "UNAVAILABLE":
        raise RuntimeError("Regulations MCP must remain unavailable without a provider")

    commerce = await call_tool(
        arguments.commerce_url,
        token,
        "find_confirmed_offers",
        {"category": "PLANT", "candidate_id": "plant-spider", "zip_code": "10001"},
    )
    if commerce.is_error or not commerce.structured_content:
        raise RuntimeError("Commerce MCP smoke call failed")
    if commerce.structured_content.get("status") != "UNAVAILABLE":
        raise RuntimeError("Commerce MCP must remain unavailable without a provider")

    care_plan = await call_tool(
        arguments.care_plan_url,
        token,
        "preview_care_plan",
        {
            "session_id": "c0a8012e-6d1a-4c8b-9fcb-6d27ea0cb911",
            "recommendation_id": "plant-spider",
            "category": "PLANT",
            "item_name": "Spider Plant",
            "start_date": "2026-09-12",
            "timezone": "America/New_York",
        },
    )
    if not care_plan.is_error:
        raise RuntimeError("Care Plan MCP accepted a mutation without an IAP user assertion")

    print("catalog=ok regulations=unavailable commerce=unavailable care_plan_auth=required")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-url", required=True)
    parser.add_argument("--regulations-url", required=True)
    parser.add_argument("--commerce-url", required=True)
    parser.add_argument("--care-plan-url", required=True)
    return parser.parse_args()


def main() -> int:
    asyncio.run(run(parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
