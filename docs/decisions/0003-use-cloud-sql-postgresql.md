# ADR 0003: Use Cloud SQL for PostgreSQL as the transactional store

- Status: Accepted
- Date: 2026-09-05

## Context

The API needs durable catalog and care-plan persistence without coupling application services to
a cloud provider. Production connections must avoid long-lived database credentials, migrations
must be controlled independently from API startup, and concurrent care-plan updates must not
silently overwrite each other.

## Decision

Use PostgreSQL 17 locally and Cloud SQL for PostgreSQL 17 in Google Cloud. Keep SQLAlchemy models
and repositories behind the existing provider-neutral ports. Use `asyncpg` for API traffic and the
Cloud SQL Python Connector with automatic IAM database authentication in hosted environments.

Run Alembic migrations as a separate release job. The API only verifies connectivity and the exact
schema revision during startup. Store application tables and Alembic state in the dedicated
`advisor` schema. Confirming a care-plan preview consumes the preview and inserts the plan in one
transaction; later plan mutations use an optimistic version check.

Use private IP and same-region runtime connectivity in production. Runtime identities receive data
access only; a separate migration identity owns schema changes.

## Consequences

- API replicas share authoritative catalog and care-plan state.
- Failed or concurrent preview confirmations cannot leave a consumed preview without its plan.
- A stale or unmigrated database prevents the API from becoming ready.
- Local development can continue with in-memory adapters or the PostgreSQL Compose service.
- Cloud SQL resources, private networking, IAM users, and release jobs remain infrastructure work;
  no cloud resource is created by the application process.
- Ownership columns remain nullable only for the authentication expand phase and must be enforced
  before public deployment.
