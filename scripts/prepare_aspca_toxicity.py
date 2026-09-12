"""Convert a reviewed ASPCA DOCX compilation into deterministic structured JSON."""

import argparse
from datetime import datetime
from pathlib import Path

from services.ingestion.toxicity import ToxicityStatus, build_aspca_dog_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()

    if args.reviewed_at.tzinfo is None:
        parser.error("--reviewed-at must include a timezone")
    dataset = build_aspca_dog_dataset(
        args.source.resolve(strict=True), reviewed_at=args.reviewed_at
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
    toxic = sum(record.toxicity_status is ToxicityStatus.TOXIC for record in dataset.records)
    non_toxic = sum(
        record.toxicity_status is ToxicityStatus.NON_TOXIC_LISTED for record in dataset.records
    )
    print(
        f"records={len(dataset.records)} toxic={toxic} non_toxic_listed={non_toxic} "
        f"version={dataset.source.content_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
