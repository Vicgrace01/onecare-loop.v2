# OneCare Loop v2 — architecture

## Product boundary

OneCare Loop is a care-coordination and referral-closure system for a hypertension pathway. It records screening, referral, facility response, appointment, attendance, clinician disposition and follow-up performed by authorised people. It is not a diagnostic engine, prescribing system or emergency dispatch service.

## Deployment shape

A modular monolith is used deliberately: one deployable FastAPI application with clear internal boundaries and one relational database. The current runtime targets local SQLite for development and PostgreSQL for hosted deployment. PostgreSQL operational validation remains Part 3 work.

```text
Clients
   |
FastAPI /api/v1
   |
Bearer auth + request dependencies + organisation checks
   |
Care use cases / services
   |
Domain state machine + signed event ledger
   |
SQLAlchemy 2 / caller-owned transaction
   |
SQLite (local) | PostgreSQL (target deployment)
```

## Layer responsibilities

- `app/api`: HTTP routes, dependencies, response contracts and error mapping.
- `app/schemas`: validated Pydantic request/response models.
- `app/services`: application use cases for auth, privacy, care workflow and FHIR conversion.
- `app/domain`: state-transition invariants, event canonicalisation, hashing, signing and verification.
- `app/db`: SQLAlchemy mappings, engine, foreign-key configuration and session lifecycle.
- `app/core`: configuration, password hashing and bearer-token primitives.
- `migrations`: explicit Alembic schema evolution.
- `tests`: auth, permission, domain, persistence, cryptographic and end-to-end workflow tests.

## State and event model

A positive hypertension screen starts the care path:

`SCREEN_POSITIVE → REFERRAL_CREATED → FACILITY_ACCEPTED → APPOINTMENT_BOOKED → CLINICAL_ENCOUNTER_COMPLETED → CLINICAL_DISPOSITION_RETURNED`.

The longitudinal path starts after a clinician disposition:

`FOLLOWUP_DUE → REPEAT_ASSESSMENT → BP_CONTROL_RECORDED → FOLLOWUP_DUE ...`.

Negative and inconclusive screenings are first-class recorded outcomes and do not create a referral. Failure states are explicit events; redirection and rebooking append new events and preserve the failed or previous attempt. A new screening episode is allowed only after a defined terminal/recoverable state. After attendance, a clinician records a confirmatory assessment or a reason it is not indicated before returning a disposition. Referral owner and assignment time are persisted separately, while ownership changes are also recorded in the event history. SLA exceptions are operational records created by the idempotent CLI processor and require a scheduled invocation; the web process does not run a background worker.

Each patient has one ordered event chain across care episodes. An event hash commits to identity, sequence, patient, referral, type, actor ID/role, canonical payload, previous hash, timestamp and actor public key. Ed25519 signs the event hash. A separate ledger head tracks the current sequence and digest. Verification recalculates the chain and signatures. Only event types defined as domain workflow states determine the current workflow state; supplementary events (messages, acknowledgements, consent, confirmatory assessment and ownership assignment) do not override it. Appends lock the patient row before the ledger head to serialize first and subsequent writes on databases that support row locks. This is tamper-evident, not tamper-proof against an administrator with complete database and signing-key control.

## Transaction boundary

The API request owns a SQLAlchemy transaction. Care services read the current state, validate the requested transition and write domain rows plus ledger event in that same transaction. A failed state guard or database write rolls all related mutations back. PostgreSQL row-level locking is used where supported; SQLite is intended for local development and low-concurrency demonstrations.

## Identity and organisation authority

- Public registration always creates a patient account.
- Staff accounts are provisioned by an administrator and assigned to a matching organisation type.
- Each authenticated request reloads the current user and role from the database; inactive accounts are rejected.
- Operational routes derive the actor from the token. A client cannot assert a different actor ID or role in JSON.
- Pharmacy/PMV users can screen and refer only their organisation's cases. Hospital actions are restricted to the receiving facility. Consultation threads are scoped to the referral's two care organisations. A clinician must match the clinician assigned to the encounter to return its disposition.
- Patients can access only their own patient-token endpoints and records. Administrators have separately gated cross-patient audit access.

## Privacy and key boundaries

Phone, display name, demographics, measurements, clinical notes, disposition text, event payloads, consultation messages, notification body and alert notes are encrypted with per-patient data keys. Those data keys are wrapped with the PII key. Consent revocation destroys the wrapped key, rotates contact lookup material, disables the patient account and clears any linked account-email ciphertext. The chain remains verifiable, while protected historical event content becomes unavailable to the application.

Account emails are encrypted using the dedicated PII encryption key and indexed with a keyed digest; the clear address is not stored in new indexed identity fields. The PII key and signing master key must be distinct in production. Legacy pre-v2 user rows are upgraded on successful login because migrations do not possess deployment secrets needed for encryption.

## External services and runtime truthfulness

Eligibility responses are stored as `unknown` without a live NHIA/DHIN endpoint. Notification rows are marked simulated and the provider is not called. Red-flag alerts are recorded only; dispatch is disabled. Follow-up plans are persisted and manual; no background scheduler runs. FHIR functionality is an authenticated R4 collection Bundle export, not a full FHIR server. These boundaries are shown in the API and documented in `care-workflow.md`.

## Web application and delivery

The user interface is a dependency-light, same-origin web client served by FastAPI:

- `app/web/index.html` is the application shell.
- `app/web/assets/css/app.css` defines the responsive interface, forms, tables and accessibility states.
- `app/web/assets/js/app.js` handles authentication, role-specific navigation and API calls.
- `/assets/*` serves the static assets; `/` serves the web application.

The UI uses the same versioned API as external clients. Staff actions use the currently authenticated bearer token. Tokens are kept in tab-scoped `sessionStorage`; all API input is still validated server-side. CSP and related browser security headers are set by the FastAPI middleware.

Deployment files include `Dockerfile`, `compose.yaml`, `.dockerignore`, `.github/workflows/ci.yml` and `deploy/production-checklist.md`. Use `python -m app.cli create-admin` after applying database migrations to bootstrap an administrator on a fresh non-demo deployment.


## Web interface

The same-origin FastAPI web client preserves the original OneCare visual direction without using the old Flask templates. `app/web/assets/css/heritage.css` carries the brand palette, typography, animated six-stage illustration, dashboard/auth themes and patient journey ring. `app/web/assets/js/heritage-motion.js` provides low-dependency reveal/stagger effects, particles, button ripple, numeric count-ups, desktop cursor and magnetic actions, with reduced-motion and touch fallbacks. `app/web/assets/js/app.js` renders the ring from canonical ledger events; the visual stage indicator is not itself authoritative. The implementation does not import the former GSAP/ScrollTrigger/Lenis runtime.
