# Database migrations

Migrations run as a separate release step and never during API startup.

Set `MIGRATION_DATABASE_URL` to a SQLAlchemy `postgresql+psycopg://` URL, usually through the Cloud SQL Auth Proxy or a private-IP deployment job, then run:

```powershell
uv run alembic upgrade head
```

The runtime verifies that the database is at the expected revision and fails startup on drift.
