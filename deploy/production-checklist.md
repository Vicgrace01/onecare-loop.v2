# Production deployment checklist

This project has a local Docker Compose profile. A real deployment is not production-approved merely because the container starts.

## Before deployment

- Choose a Nigerian data-hosting region and obtain written residency/vendor review.
- Generate distinct `SECRET_KEY`, `SIGNING_MASTER_KEY` and `PII_ENCRYPTION_KEY` values from an approved secrets manager. Never commit `.env`.
- Set `APP_ENV=production`, `AUTO_CREATE_SCHEMA=false`, `SEED_DEMO_ADMIN=false`, and a PostgreSQL `DATABASE_URL`.
- Set a strong `POSTGRES_PASSWORD`; do not use Compose's local-development credentials in production.
- Apply Alembic migrations as a controlled one-off release job before starting new web replicas.
- Configure TLS at a trusted reverse proxy/load balancer. Restrict access to port 8000 to that proxy.
- Configure encrypted PostgreSQL storage, private networking, backups, point-in-time recovery and restore drills.
- Establish KMS/HSM-backed key storage and documented rotation/escrow/recovery procedures; current application configuration uses environment-provided keys.
- Configure rate limiting and abuse monitoring at the edge, alerting, audit retention, incident response and log redaction.
- Obtain clinical governance approval of screening thresholds, red-flag protocols, follow-up wording and clinician roles.
- Complete NDPA legal review, DPIA, data-subject process, retention schedule and cross-border transfer review.
- Connect and validate SMS, NHIA/DHIN, claims and emergency-response integrations under signed provider agreements. They are not live in this repository.

## Local Compose smoke test

```powershell
Copy-Item .env.example .env
# Edit .env and set POSTGRES_PASSWORD and three separate long secrets.
docker compose up --build
```

Open `http://localhost:8000`. The Compose command runs Alembic before Uvicorn. The initial administrator must be provisioned through a controlled bootstrap process; demo seeding is disabled in the production container profile.

For actual multi-replica production, run `alembic upgrade head` once in a release job, not independently in every replica's startup command. Use a managed PostgreSQL service and a secrets manager instead of this local Compose stack.
