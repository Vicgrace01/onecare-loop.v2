# Original repository audit — `Vicgrace01/onecare-loop`

Audit basis: repository tree inventory showed **113 tracked files** at the inspected revision. The original project was a Flask/SQLite modular monolith. Core backend modules, the state machine, ledger/signing, screening and hospital services, routes, authentication, major app templates and JavaScript, CSS entrypoints, tests, README and repair scripts were inspected to guide this rebuild. The replacement is now a combined FastAPI application with its responsive web surface, migrations, documentation and CI configuration.

## Product behaviour to preserve

1. Pharmacy/PMV hypertension screening, with an explicit protocol version and consent record.
2. Referral creation, urgency and a deadline/SLA.
3. Facility acceptance or decline, including an explicit re-routing path.
4. Appointment booking and human attendance attestation.
5. Clinician-signed disposition and patient-visible receipt.
6. Longitudinal follow-up after the initial referral closes.
7. A per-patient ordered event history, signature verification, red-flag acknowledgement, FHIR export and operational reporting.
8. Explicit simulation boundaries for eligibility, SMS/WhatsApp, emergency paging, payer reimbursement and synthetic risk scoring.

## High-risk findings from the original code

| Area | Finding | Rebuild response |
|---|---|---|
| Signup and roles | `/auth/signup` accepted a caller-selected role and defaulted to `admin` if omitted. | Public registration always creates `patient`; staff provisioning is administrator-only; no public admin creation. |
| Actor identity | Several routes accepted `actor_id` from JSON and passed it to services. Hospital services could also create placeholder users with fake password hashes. | Authenticated user identity is sourced from the request context and stored as the event actor. No fake users are auto-created. |
| State transitions | The current state was read on one DB connection, then the event was appended on another. | State validation and ledger append share one SQLAlchemy transaction and use a locked ledger head where the database supports it. |
| Domain writes | Some original hospital workflows wrote appointment/encounter/disposition records separately from the corresponding ledger transition. | FastAPI use cases commit related business records and events within one SQLAlchemy request transaction; rollback tests cover failed transitions. |
| Runtime defaults | Development mode was enabled by default and the fallback Flask secret was known. | Production settings reject the development secret, demo seeding and automatic schema creation. |
| Patient receipt | A public patient-ID URL returned the patient receipt. OTP endpoints existed, but the public receipt URL bypassed them. | Patient receipts require the authenticated patient owner or an authorised staff member; the patient portal uses OTP verification. |
| OTP | OTP generation used the non-cryptographic `random` module, and OTP hashing was unsalted SHA-256. | FastAPI uses a cryptographically secure code generator, keyed hash, expiry and attempt limits. Live OTP delivery and a complete production abuse-control stack remain outstanding. |
| Password/session lifecycle | Password hashing existed, but role selection and broader actor handling weakened the benefit. | Argon2id password hashing; short-lived signed bearer tokens; roles reloaded from the database on every request. |
| Schema evolution | `models.py` mixed the schema and idempotent `ALTER TABLE` calls, using SQLite-only mechanisms. | SQLAlchemy 2 mappings with explicit Alembic migrations; PostgreSQL is the hosted target. |
| Cryptographic claims | The original README correctly noted that a DB owner could rewrite the full chain and that server-held keys were a limitation. | Retain the honest tamper-evident claim; encrypt private signing keys and explicitly document the remaining trust boundary. External key management and anchoring remain production work. |
| Metrics | Dashboard revenue recovery used a hard-coded simulated naira value. | Any such figure remains labelled simulated until connected to a signed payer agreement/remittance dataset. |
| Clinical messaging | Simulated SMS, eligibility and emergency alerts were represented through local records, not live provider delivery. | Preserve the distinction between a local simulation and a real integration in API responses, docs and UI. |
| Root clutter | One-off repair scripts, snapshots, code dumps and duplicate text copies were committed beside the running app. | Keep migrations, tests, docs and source in explicit folders; do not ship generated dumps or patch scripts as runtime code. |

## Existing source elements and intended destination

| Original area | Destination in v2 |
|---|---|
| `app.py`, `routes/` | `app/main.py`, `app/api/v1/` |
| `models.py` | `app/db/models.py`, `migrations/` |
| `services/loop.py` | `app/domain/states.py` |
| `services/ledger.py`, `services/signing.py` | `app/domain/ledger.py` |
| `services/auth.py`, `services/crypto.py` | `app/services/auth.py`, `app/core/security.py`, encrypted contact service in Deliverable 2 |
| `services/screening.py`, `services/referral.py`, `services/hospital.py`, `services/longitudinal.py` | `app/services/care.py` and the focused routers under `app/api/v1/` |
| `services/longitudinal.py` | Follow-up use cases in `app/services/care.py` and `app/api/v1/followups.py` |
| `services/fhir.py` | `app/services/fhir.py` and `app/api/v1/fhir.py` |
| `services/sms.py`, `services/templates.py`, `services/classifier.py` | Simulated notification and care-team messaging use cases in `app/services/care.py` and `app/api/v1/communications.py` |
| `templates/`, `static/` | Same-origin responsive application in `app/web/` |
| `tests/`, `smoke_test.py`, `verify_all.py` | Consolidated pytest suite and integration tests under `tests/` |
| `README.md`, compliance/model pages | `README.md` and maintained `docs/` pages; claims revalidated against implementation |

## Additional issues corrected in the final FastAPI integration

- **Supplementary-event isolation:** the old ledger reader treated every latest event as the current care state. FastAPI now derives the next legal workflow state only from canonical domain-state events; messages, acknowledgement, consent, confirmatory records and owner assignments remain supplementary signed history.
- **Confirmatory step:** the assigned clinician must record a repeat-office, home-monitoring or ambulatory-monitoring method, or document why it is not indicated, before returning a disposition.
- **Referral ownership:** acceptance assigns the facility operator; attendance assigns the clinician; reassignment is constrained to active staff in the same receiving organisation.
- **Overdue and unassigned visibility:** the hospital/admin attention surface shows unassigned open referrals and overdue SLA exceptions. An idempotent CLI processor creates operational exceptions when externally scheduled; it does not page staff or move clinical state.
- **Recovery:** a declined/unavailable referral can be redirected later without erasing the original failure. The new referral gets a new identifier, fresh SLA and an explicitly unknown/simulated eligibility record.

These changes are covered by regression and integration tests. See `docs/care-workflow.md` and `docs/competition-demo-guide.md` for the final contract and judge walkthrough.

## Rebuild rule

Existing behaviour is not automatically preserved when it depends on an unsafe trust boundary, partial writes, a misleading simulation claim or a shortcut that bypasses consent. The replacement preserves the care pathway and user-facing value, but it intentionally tightens the actor, data and transaction rules.
