# Contract compatibility notes

## 2026-09-11: authenticated v1 ownership boundary

- All `/v1` product endpoints now require a Google IAP signed assertion in the deployed service.
- The versioned `AUTHENTICATION_REQUIRED` error uses the existing v1 error envelope and HTTP 401.
- Care-plan request and response bodies are unchanged; ownership is derived from the verified identity
  and is never accepted from the client.
- `/api/v1` is a same-origin web alias and is intentionally omitted from OpenAPI. `/v1` remains the
  canonical versioned contract.
- `CAT` remains present in v1 for compatibility but is disabled in the shipping configuration until
  reviewed Cat content passes the same safety and retrieval gates.
