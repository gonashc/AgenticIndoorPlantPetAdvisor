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

MCP endpoints are separately enabled with `MCP_MODE=remote`. Plant and adoption services can be
enabled independently. The application can call only `find_places` and `find_adoptions`, requests
at most three results, accepts only structured output, and rejects non-HTTPS sources or invalid
verification timestamps.

The deployed plant-location service uses Google Places Text Search (New) only to discover nearby
nurseries. A returned place is not evidence that a particular plant is in stock. The service is a
private Cloud Run endpoint, the API calls it with a short-lived service-identity token, and its API
key is restricted to `places.googleapis.com` and stored in Secret Manager. Deploy it with
`scripts/bootstrap_places_mcp_gcp.ps1` followed by `scripts/deploy_places_mcp.ps1`; deployment also
rebuilds the API revision with the private MCP URL and audience configured. Configure a Places API
quota alert in Google Maps Platform before widening access beyond the demo users.

The adoption MCP exposes only `find_adoptions` for `DOG` and `CAT`. It searches the public
RescueGroups available-animal view within a configured ZIP-code radius after profile ranking and
returns at most three recently observed links. It does not guarantee availability, temperament,
health, or profile suitability; it does not persist or index provider data. Only HTTPS links under
the configured adoption host allowlist are returned.

Request a public RescueGroups API key, add `RESCUEGROUPS_API_KEY` to the ignored `.env`, and run
`scripts/bootstrap_adoption_mcp_gcp.ps1`. The bootstrap copies the key into Secret Manager and
grants only the dedicated adoption runtime identity access. Deploy with
`scripts/deploy_adoption_mcp.ps1`; the script keeps the existing Places MCP configured and updates
the API to call both private services with short-lived Cloud Run identity tokens.

The climate MCP exposes `get_weather` over latitude/longitude and returns the current hourly NWS
forecast plus at most three active alerts. It uses only the official `api.weather.gov` host in
production, follows only provider-discovered URLs on that host, and supplies the identifying
User-Agent required by NWS. Its output is explicitly advisory and cannot alter hard exclusions or
authoritative scores. Run `scripts/bootstrap_climate_mcp_gcp.ps1` and
`scripts/deploy_climate_mcp.ps1` to create its dedicated identity and private Cloud Run service.

The API does not invoke Climate MCP yet. The current questionnaire provides a ZIP code, while NWS
requires coordinates. Connect this service only after a reviewed ZIP-to-coordinate boundary is
available; do not let an LLM invent or resolve coordinates.
