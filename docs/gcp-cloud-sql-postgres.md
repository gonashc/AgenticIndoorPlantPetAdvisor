# Google Cloud SQL for PostgreSQL

## Target topology

- Cloud SQL for PostgreSQL 17 in the same region as the API runtime.
- Regional high availability for production and zonal instances for disposable development.
- Private IP with Cloud Run Direct VPC egress or an appropriate Serverless VPC Access connector.
- Point-in-time recovery, automated backups, deletion protection, maintenance windows, and database flags reviewed before launch.
- A dedicated runtime service account and a separate migration identity.
- Cloud SQL Python Connector with automatic IAM database authentication and Application Default Credentials.

The connector secures and authorizes the connection; it does not create a network path. A private-IP deployment still needs VPC connectivity.

## Application configuration

```text
APP_ENV=production
DATABASE_MODE=cloud_sql
INSTANCE_CONNECTION_NAME=project-id:us-east1:advisor-postgres
DB_USER=advisor-api@project-id.iam
DB_NAME=advisor
CLOUD_SQL_ENABLE_IAM_AUTH=true
CLOUD_SQL_IP_TYPE=PRIVATE
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=2
DB_POOL_TIMEOUT_SECONDS=30
DB_POOL_RECYCLE_SECONDS=1800
```

Do not set `DB_PASSWORD` when automatic IAM authentication is enabled. If password authentication is temporarily required, source the password from Secret Manager rather than committing it or placing it in deployment manifests.

The runtime identity needs `roles/cloudsql.client`. Automatic IAM database authentication additionally requires the appropriate Cloud SQL Instance User permission and a matching IAM database user. Enable the Cloud SQL Admin API in the owning project.

## Migrations

Migrations are a separate release job. Connect the job through private networking or the Cloud SQL Auth Proxy and expose a short-lived `MIGRATION_DATABASE_URL` using the `postgresql+psycopg://` dialect:

```powershell
uv run alembic upgrade head
```

Use an administrative migration role to create the `advisor` schema and tables. Grant the runtime role only the required schema usage and table/sequence permissions. Do not grant the runtime role schema ownership or migration privileges.

The API validates its required schema capabilities at startup and refuses to serve traffic when
the database is missing a required table or column. Forward-compatible revisions remain eligible
so a previous application image can still be used for rollback.

## Local PostgreSQL

Start PostgreSQL 17:

```powershell
docker compose up -d postgres
$env:MIGRATION_DATABASE_URL = "postgresql+psycopg://advisor:advisor@127.0.0.1:5432/advisor"
uv run alembic upgrade head
$env:DATABASE_MODE = "url"
$env:DATABASE_URL = "postgresql+asyncpg://advisor:advisor@127.0.0.1:5432/advisor"
uv run uvicorn advisor_api.application:app --reload
```

The PostgreSQL catalog is empty after migration. Keep `DATABASE_MODE=memory` for UI development until Engineer 3's ingestion or an explicitly development-only seed process is added.

## Ownership enforcement

Migration `0004_care_plan_ownership` assigns any earlier anonymous demo rows to an unreachable legacy
principal and makes `owner_id` non-null. New previews and plans derive their owner from a verified IAP
assertion, and every read, confirmation, and mutation includes the owner predicate. Client payloads
cannot provide or change ownership.
