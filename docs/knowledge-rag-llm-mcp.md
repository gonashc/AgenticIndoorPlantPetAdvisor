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

Production keeps `EXPLANATION_MODE=deterministic` unless one exact model passes the manual
`Explanation model release gate` GitHub workflow. The workflow first runs the deterministic safety
and ranking suite, then exercises the selected model through strict structured output across all
three categories with bounded synthetic evidence and a prompt-injection canary. It uploads a
versioned approval report bound to the exact Git commit, model, prompt, dataset, and suite. An
OpenAI-mode deployment must supply that report to `deploy_current.ps1`; a missing, failed, stale,
or mismatched report is rejected before the image is built. The production adapter uses the
Responses API, strict JSON Schema output, low reasoning effort, and no response storage. Runtime
generation failures still fall back visibly to deterministic explanations.

The initial release-gate candidate is `gpt-5.6-terra`; model activation is not implied by adding
the workflow or a secret. Add `OPENAI_API_KEY` as a protected GitHub environment secret and add the
same value to Secret Manager as `openai-api-key` only when ready to run the paid gate. After a
successful workflow, download `explanation-release-report.json` and deploy with:

```powershell
./scripts/deploy_current.ps1 `
  -ExplanationMode openai `
  -OpenAiModel "gpt-5.6-terra" `
  -ExplanationApprovalFile "path/to/explanation-release-report.json" `
  -McpMode remote `
  -McpCarePlanUrl "https://CARE_PLAN_SERVICE_URL/mcp" `
  -McpCarePlanAudience "https://CARE_PLAN_SERVICE_URL" `
  -GcloudPath $gcloud
```

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

## Catalog, regulations, commerce, and care-plan MCP boundaries

Four additional MCP service boundaries are implemented but are not yet connected to the
recommendation graph:

- Catalog exposes only exact-ID, bounded reads for approved profiles, deterministic constraints,
  structured toxicity, and provenance. PostgreSQL remains authoritative. It provides no arbitrary
  query or ranking tool and its production database role must be read-only.
- Regulations exposes `lookup_pet_regulations` for one selected pet category and jurisdiction.
  Results accept only HTTPS government sources (plus explicitly allowlisted municipal hosts) and
  retain a source version. Its provider is disabled until a reviewed adapter can turn current
  sources into versioned rule records; web-search snippets are not silently promoted to rules.
- Commerce exposes `find_confirmed_offers` for one already-selected candidate and returns at most
  three allowlisted, recently observed offers. Its provider is disabled until a retailer contract
  permits confirmed inventory, price, and pickup data. This remains optional for the demo.
- Care Plan exposes preview, confirmed creation, pause/reactivate, and task-completion tools by
  delegating to the existing `CarePlanService`. It never accepts an owner ID. The private caller
  must forward the original `X-Goog-IAP-JWT-Assertion`, which the service verifies before deriving
  the owner. Creation still requires the literal `confirmed: true` input.

The API composition root configures an authenticated Care Plan MCP client with
`MCP_CARE_PLAN_URL` and `MCP_CARE_PLAN_AUDIENCE`. The client obtains a short-lived Cloud Run ID
token for service authentication and forwards the signed IAP assertion only in transport metadata;
it never converts identity into an MCP tool argument. Existing versioned care-plan HTTP endpoints
remain the React application's public contract. When the private endpoint is configured, those
REST handlers route preview, confirmed creation, retrieval, adjustment, and task completion through
MCP. The MCP service returns a discriminated v1 result for known domain failures, and the gateway
reconstructs the same HTTP 404/409/422 status, code, message, and details without leaking owner IDs.
Transport and malformed-result failures become the existing v1 503 service-unavailable envelope.

Each service has a separate ASGI entry point, non-root container, strict output models, bounded
request sizes, DNS-rebinding protection, a health route, and CI contract tests. Deployment remains
separate from graph enablement: establish least-privilege Cloud SQL roles for Catalog and Care Plan,
select and evaluate Regulations/Commerce providers, then add only the tools needed for the selected
category and intent to the MCP gateway allowlist.

Bootstrap the dedicated identities and Cloud SQL IAM users, then build and deploy the four private
services with:

```powershell
$gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
./scripts/bootstrap_internal_mcps_gcp.ps1 -GcloudPath $gcloud
./scripts/deploy_internal_mcps.ps1 -GcloudPath $gcloud
```

The deployment runs a dedicated Cloud Run job under the migration identity to grant Catalog only
`SELECT` access to its authoritative tables and Care Plan only transactional access to its plan
tables. It grants the API runtime identity permission to invoke each private service, but it does
not connect the new tools to the graph. Regulations and Commerce remain visibly degraded until
their provider settings and reviewed adapters are implemented.

Deploy the Care Plan MCP revision before the API revision. The updated REST facade sends a
`request_id` tool argument and requires the MCP 1.1 discriminated result contract. Then rebuild
the API with the existing Places/Adoption settings plus the private Care Plan endpoint:

```powershell
./scripts/deploy_current.ps1 `
  -McpMode remote `
  -McpCarePlanUrl "https://CARE_PLAN_SERVICE_URL/mcp" `
  -McpCarePlanAudience "https://CARE_PLAN_SERVICE_URL" `
  -GcloudPath $gcloud
```

Regulations cannot be promoted merely by adding web search: current rules must be normalized into
reviewed, source-versioned records from government pages. Commerce remains intentionally excluded
from the demo path until a retailer API contract confirms inventory, price, and pickup availability.
