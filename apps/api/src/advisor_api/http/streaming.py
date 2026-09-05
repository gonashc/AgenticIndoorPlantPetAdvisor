"""Server-Sent Event serialization and reconnection helpers."""

import json

from advisor_api.contracts.streaming import RecommendationStreamEvent


def encode_sse(event: RecommendationStreamEvent) -> str:
    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"id: {event.event_id}\nevent: {event.event}\nretry: 3000\ndata: {payload}\n\n"


def sequence_from_last_event_id(last_event_id: str | None) -> int:
    if not last_event_id:
        return 0
    _, separator, sequence = last_event_id.rpartition(":")
    if not separator or not sequence.isdigit():
        return 0
    return int(sequence)
