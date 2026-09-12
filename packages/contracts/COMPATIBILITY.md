# Contract compatibility notes

## 2026-09-12: additive live advisory context and traffic contract

- Recommendation responses add optional `live_advisories` entries for climate, regulation, and
  allowlisted web guidance. These entries are advisory only and cannot affect candidates, scores,
  hard exclusions, or validation of reviewed evidence.
- HTTP 429 now uses the existing v1 error envelope with code `RATE_LIMIT_EXCEEDED` and a standard
  `Retry-After` header.
- Regulations MCP v1 can return `DISCOVERY_ONLY` plus `discovery_sources`. Search snippets remain
  separate from the authoritative `rules` collection and are never promoted automatically.
- Existing request bodies and required recommendation fields are unchanged.

## 2026-09-11: authenticated v1 ownership boundary

- All `/v1` product endpoints now require a Google IAP signed assertion in the deployed service.
- The versioned `AUTHENTICATION_REQUIRED` error uses the existing v1 error envelope and HTTP 401.
- Care-plan request and response bodies are unchanged; ownership is derived from the verified identity
  and is never accepted from the client.
- `/api/v1` is a same-origin web alias and is intentionally omitted from OpenAPI. `/v1` remains the
  canonical versioned contract.
- `CAT` remains present in v1 for compatibility but is disabled in the shipping configuration until
  reviewed Cat content passes the same safety and retrieval gates.
