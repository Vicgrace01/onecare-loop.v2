# OneCare Loop v2

**A referral cannot quietly disappear between a community pharmacy, hospital, clinician, patient and payer.**

OneCare Loop is a care-coordination and referral-closure platform for a hypertension pathway. It records the handoffs from a community screening through referral, hospital acceptance, appointment, attendance, clinician disposition and follow-up. Each patient journey is represented by a signed, hash-chained event history so changes can be detected and the sequence can be verified.

This is a clean replacement for the original Flask prototype. The new application is a modular FastAPI monolith with SQLAlchemy 2, Pydantic 2 and Alembic. It is built as a single deployable service without splitting a prototype into premature microservices.

## Current release status

| Area | Status |
|---|---|
| FastAPI application, data model and migrations | Implemented |
| Hypertension screening-to-follow-up workflow | Implemented as a prototype; clinical review is still required |
| Responsive web interface and one-click synthetic judge demo | Implemented locally |
| Automated tests and CI | Regression fixes are being verified in GitHub Actions |
| Hosted deployment | Not yet deployed |
| Live NHIA/DHIN, SMS/WhatsApp, claims and emergency dispatch | Not connected; provider agreements and integration validation are still required |

The application is a single deployable FastAPI service. Its web interface is served by FastAPI; there is no separate Node frontend server. The interactive API reference is available at `http://127.0.0.1:8000/docs` when running in development mode.

## Product workflow

```text
Patient consent + pharmacy/PMV screening
                  |
          Positive BP result
                  |
          Referral created
                  |
      Receiving hospital accepts
                  |
         Appointment booked
                  |
       Attendance attested
                  |
 Clinician records confirmatory assessment
      or documented not-indicated reason
                  |
    Assigned clinician disposition
                  |
          Follow-up scheduled
                  |
       Repeat BP assessment
                  |
        BP control recorded
```

A negative or inconclusive screen is recorded but does not create a referral. Failure cases are explicit events: facility decline/unavailability, patient unreachable/decline, appointment missed and patient reschedule request. Recovery creates new events; it does not silently rewrite the event history.

## Architecture

```text
app/
  api/         FastAPI routes, dependencies and error mapping
  core/        configuration and authentication primitives
  db/          SQLAlchemy models, engine and session lifecycle
  domain/      care state machine and signed event ledger
  schemas/     Pydantic request/response contracts
  services/    authentication, privacy, care workflows and FHIR mapping
migrations/    Alembic schema history
  versions/    initial schema, integrity constraints, workflow/privacy, email encryption
tests/          auth, permissions, domain, crypto, schema, care-journey, UI and Chromium browser tests
docs/           architecture, care workflow, judge guide, operator guide and security review
```

### Engineering decisions

- **Modular monolith:** one application and one transaction boundary, with separate domain, service, HTTP and persistence layers.
- **Database constraints:** the database enforces key role, state, urgency, BP-range and appointment invariants in addition to application validation.
- **Authenticated actors:** API endpoints derive the actor and role from the verified bearer token. Client-supplied actor IDs/roles are not trusted.
- **Organisation boundaries:** pharmacy/PMV users can work only on screenings from their own organisation; hospital actions are scoped to the receiving facility; consultation messages are scoped to the referral's care organisations; clinicians can submit the disposition only for the encounter assigned to them.
- **Atomic workflows:** the state check, event append and related business records share the SQLAlchemy transaction. A failed transition or write rolls the complete operation back.
- **Workflow-state isolation:** only canonical care-state events determine the next legal transition. Messages, acknowledgement, consent, confirmatory records and ownership changes remain signed supplementary events and cannot silently replace the workflow state.
- **Owned referral progression:** accepted referrals receive a facility owner; attendance assigns the clinician; administrators and hospitals can reassign within the receiving organisation. The clinician worklist is assignment-scoped.
- **Clinician-confirmed follow-up:** after attendance, the assigned clinician records a confirmatory assessment method or documents why another measurement is not indicated before returning a disposition. The software does not choose the clinical method.
- **SLA exception processing:** overdue open referrals can be scanned by `python -m app.cli escalate-overdue`. The command is designed for an external scheduler and creates an idempotent operator exception; it does not page a human or move the clinical state automatically.
- **Tamper evidence:** events are linked by SHA-256 hashes and signed with Ed25519. The event digest includes the actor public key. The system is tamper-evident, not tamper-proof against a database/application administrator who controls the signing keys and all stored records.
- **PII separation:** patient contact, display name, demographics, measurements, clinical notes, dispositions, messages and notification bodies use patient-scoped encryption keys. Account emails are encrypted separately; lookup uses a keyed digest rather than plaintext email.

## Visual interface and motion

The FastAPI application keeps the original OneCare Loop visual identity rather than importing the Flask templates or their legacy routes. The current interface brings back the deep-navy/teal/peach palette, Bricolage Grotesque / Public Sans / IBM Plex Mono typography, six-part animated loop illustration, split-screen authentication treatment, stage-by-stage patient journey ring, ambient particle field, staggered reveals, ripple feedback, count-up metrics, desktop cursor treatment and subtle magnetic primary actions. The SPA uses native View Transitions when the browser supports them and CSS/JavaScript fallbacks elsewhere.

These effects are implemented with CSS and lightweight browser JavaScript; the FastAPI release does **not** depend on the original external GSAP, ScrollTrigger or Lenis runtime. This avoids coupling the redesigned frontend to legacy Flask templates and third-party animation scripts. Native smooth scrolling is used where supported. Touch devices do not receive the custom cursor or magnetic pointer effects, and `prefers-reduced-motion` disables non-essential animation. Google Fonts are loaded when network access is available; system font fallbacks remain defined.

The original six-stage ring is presentation, not a separate source of truth: the authenticated patient journey indicator is derived from recorded canonical care events. Supplementary events do not falsely advance or rewind the care stages.

## API surface

All routes are prefixed with `/api/v1`.

| Capability | Endpoints |
|---|---|
| Judge demo | `GET /demo`; `GET /demo/info`; `POST /demo/run` (synthetic-only and disabled by default) |
| Authentication | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/provision` |
| Organisation management | `POST /organisations`, `GET /organisations` |
| Screening | `POST /screenings` |
| Referral | `POST /referrals`, `GET /referrals/{id}/history` |
| Hospital operations | `GET /hospital/queue`, `/hospital/attention`; `POST /hospital/referrals/{id}/accept`, `/decline`, `/assign`, `/redirect`, `/confirmatory-assessment`, `/appointments`, `/attendance`, `/appointments/missed`, `/unreachable`, `/disposition` |
| Patient portal | `POST /patients/otp/request`, `/otp/verify`; `GET /patients/me/receipt`; `POST /patients/me/receipt/acknowledge`, `/patients/me/referrals/{id}/decline`, `/reschedule-request`; `POST /patients/{id}/consent/revoke` |
| Follow-up | `GET /patients/{id}/followups`; `POST` to the same path, `/assessment` and `/bp-control` |
| Communications | `GET /red-flags`, `POST /red-flags/{id}/acknowledge`; `POST/GET /referrals/{id}/messages`; `GET /patients/me/notifications` |
| FHIR R4 | `GET /fhir/metadata`, `GET /fhir/patients/{id}/bundle` |
| Metrics | `GET /metrics` |
| Audit | `GET /audit/patients/{id}/verify`, `GET /audit/patients/{id}/events` |
| Health | `GET /health/live`, `GET /health/ready` |

## One-click judge demo

The homepage links to `/demo`. The page calls the actual FastAPI care services to create one synthetic screening-to-follow-up journey, then animates the persisted eight-event sequence across the pharmacy, hospital, patient and clinician panels. It reports chain verification and offers a replay that does not create duplicate records. Demo reviewer emails/passwords are retrieved from configuration; passwords appear only when `DEMO_SHOW_CREDENTIALS=true`.

The demo is **disabled by default**. Enable it only in a separate synthetic-data deployment and database. It uses simulated notification records, no live NHIA/DHIN query and no financial-savings claim. See `docs/competition-demo-guide.md` for exact deployment configuration, reviewer access, walkthrough and limitations.

For local evaluator setup, copy `deploy/judge-demo.env.example` to `.env`. It contains placeholders only: generate three different application keys and set four distinct demo passwords before starting the service. It uses a separate synthetic SQLite database and disables patient self-registration. Never use this configuration with real patient information. When `DEMO_SHOW_CREDENTIALS=true`, the configured role credentials are displayed on the public demo page, so enable it only for a synthetic-data judging deployment.

See `docs/care-workflow.md` for roles, state transitions and payload boundaries; `docs/security-review.md` for implemented controls and remaining risks; and `deploy/production-checklist.md` for deployment requirements.

## Local setup — Windows PowerShell

Use Python 3.11 or newer. From the extracted project directory:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Generate separate secrets and place them in `.env`. For example, run this three times and use a different value for each secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `SECRET_KEY`, `SIGNING_MASTER_KEY` and `PII_ENCRYPTION_KEY` to different generated values. Do not commit `.env` or share production keys. A production deployment must supply a dedicated `PII_ENCRYPTION_KEY` distinct from `SIGNING_MASTER_KEY`. Leave the `DEMO_*` switches disabled for ordinary development or production. To prepare the judge demo, use the isolated synthetic deployment and follow `docs/competition-demo-guide.md`; never enable public demo credentials against a real-data database.

For a local database, leave `DATABASE_URL=sqlite:///./onecare.db`. Apply the migrations:

```powershell
alembic upgrade head
```

Run the test suite:

```powershell
python -m playwright install chromium
python -m pytest -q
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

Open:

- API documentation: `http://127.0.0.1:8000/docs`
- Liveness: `http://127.0.0.1:8000/api/v1/health/live`
- Readiness: `http://127.0.0.1:8000/api/v1/health/ready`

## Local administrator setup

No administrator is created by default. For a local-only demo, configure these values in `.env`:

```dotenv
APP_ENV=development
SEED_DEMO_ADMIN=true
DEMO_ADMIN_EMAIL=admin@onecareloop.com
DEMO_ADMIN_PASSWORD=replace-with-a-long-random-password
```

Restart the application. The demo administrator is created only when the seed flag is enabled. Production settings reject demo-admin seeding. Staff users are provisioned by an authenticated administrator and must be assigned to a matching organisation type. Public registration always creates a patient account.

## Database and deployment

SQLite supports local development and single-instance demonstrations. PostgreSQL is the target hosted database. A non-root Docker image, PostgreSQL 16 Compose profile and GitHub Actions workflow are included. The CI workflow is configured for Python 3.11 and 3.12, Chromium browser tests, migration smoke tests and a Docker image build. Check the repository's Actions tab for the current result before treating a commit as release-validated. The Compose file is intended for a local deployment smoke test, not as a fully managed production platform.

For production set `AUTO_CREATE_SCHEMA=false` and apply Alembic migrations as a controlled deployment step. Do not let every web worker mutate the schema at startup. After the database is configured and migrations are applied, create the first administrator interactively with `python -m app.cli create-admin` (or `docker compose exec web python -m app.cli create-admin` for the local Compose setup). Production has no seeded default administrator.

## Simulation and clinical boundaries

The following are explicitly **not live integrations**:

- **Eligibility:** the local adapter records `unknown` and explains that no NHIA/DHIN coverage assertion was made. No live DHIN or NHIA endpoint is called.
- **Notifications:** notification bodies are stored as simulated. No SMS, WhatsApp or voice provider is called. In development/test only, OTP responses may contain a `development_code`; production never returns the OTP.
- **Emergency alerts:** a red-flag event and acknowledgement can be recorded. `dispatch_enabled` is false; no ambulance or emergency coordinator is paged.
- **Follow-up scheduling:** follow-up plans and due dates are stored; patient reminders and follow-up transitions still require an authenticated user action. A separate `python -m app.cli escalate-overdue` command creates idempotent SLA exception records for overdue open referrals when invoked by an external scheduler. No background worker runs inside the API process, and the command does not page a coordinator.
- **Metrics:** operational referral closure and failure counts are calculated. A payer reimbursement/recovered-value figure is deliberately not invented.
- **FHIR:** the app produces authenticated FHIR R4 collection bundles for the supported workflow resources. It is not a complete FHIR server with create/update/search interactions.

OneCare Loop records screening and care coordination. It does not diagnose, prescribe, replace clinician judgement or certify that care was clinically appropriate. Screening thresholds and workflows require licensed-clinician review before use with real patients.

## Verification

The automated suite covers:

- patient-only registration, staff provisioning, encrypted email-at-rest storage and legacy-email upgrade;
- authentication, role reload and endpoint permission boundaries;
- organisation-level screening/referral/hospital isolation;
- BP validation, state-machine transitions and failure recovery;
- full pharmacy-to-hospital-to-clinician-to-follow-up journey, including confirmatory assessment gating;
- supplementary-event isolation, referral ownership, late redirection with a fresh SLA/unknown eligibility record, and idempotent SLA exception handling;
- OTP, protected receipt and acknowledgement;
- encrypted patient data, consent withdrawal/key shredding and post-erasure redaction;
- signed hash-chain verification and tamper detection;
- red-flag acknowledgement, consultation messages and FHIR export.

The browser-level tests run the application JavaScript in Chromium against a mocked browser-to-API contract; the care journey is separately covered by HTTP integration tests. Local validation has included Python compilation, JavaScript syntax checks and a fresh SQLite Alembic upgrade → downgrade → upgrade cycle. The first GitHub Actions run exposed two test-environment isolation issues and a browser-test timing race; this maintenance patch addresses those regressions. Treat a subsequent green Actions run as the CI release gate. A Docker daemon was not available for a local image build. This is prototype-level verification, not an independent security, regulatory or clinical approval.

## Before a real pilot

The security review, privacy impact assessment, retention policy, NDPA legal interpretation, clinical protocol sign-off, incident response, KMS/HSM-backed key management, external ledger anchoring, rate limiting, PostgreSQL operations, backup/restore, residency/vendor review, SMS/NHIA agreements and usability validation must be completed. Do not put real patient data into this prototype before those controls are reviewed and approved.

## License

MIT. Confirm ownership and third-party notices before release.
