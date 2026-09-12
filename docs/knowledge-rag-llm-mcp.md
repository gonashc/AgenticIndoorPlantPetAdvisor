# Knowledge, explanation, and live-data operations

The recommendation path keeps three trust domains separate:

1. PostgreSQL filters and deterministic rules decide eligibility and ranking.
2. Pinecone retrieves only reviewed, approved passages for those candidate IDs. An optional
   structured-output model explains the immutable result and may cite only supplied evidence IDs.
3. MCP tools fetch ephemeral local places or adoption listings after ranking. MCP output is never
   added to the knowledge index or used to change safety decisions.

## Approved-content ingestion

Run Alembic through revision `0002`, create a Pinecone dense index using the configured
`PINECONE_INDEX_DIMENSION` (512 by default) and `dotproduct`, and configure PostgreSQL plus
Pinecone in the ignored `.env`. The embedding output dimension must match the index. Then run:

```powershell
uv run python scripts/ingest_approved_content.py path/to/manifest.json
```

The JSON manifest has `namespace`, `allowed_licenses`, and `documents`. Each document contains the
fields represented by `ManifestDocument` in the script plus a UTF-8 `text_path` relative to the
manifest. Review timestamps must be timezone-aware; source URLs must use HTTPS; candidate IDs,
reviewer, version, approval status, and an allowlisted license are mandatory. Rejected sources are
quarantined in PostgreSQL. Accepted content is deterministically normalized, overlapped, hashed,
recorded in PostgreSQL, then replaced in Pinecone.

`DEMO_UNVERIFIED` content is accepted only when `APP_ENV` is `local` or `test`. Staging and
production ingestion accept only `AUTHORITATIVE` or `EXPERT_REVIEWED` sources.

## Safe rollout

Leave `EXPLANATION_MODE=deterministic` and `MCP_MODE=disabled` in production initially. Populate a
new versioned Pinecone namespace, run `uv run python scripts/run_recommendation_evals.py`, then run
the LangSmith experiment with `--upload`. Enable the structured model only after safety, ranking,
grounding, provenance, and degradation-disclosure checks pass. Promote the exact prompt, model,
knowledge namespace, rules, and scoring versions together.

MCP endpoints are separately enabled with `MCP_MODE=remote`. The application can call only
`find_places` and `find_adoptions`, requests at most three results, accepts only structured output,
and rejects non-HTTPS sources or invalid verification timestamps.
