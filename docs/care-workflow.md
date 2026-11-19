# Care workflow and API contract

## Purpose and scope

This service coordinates a hypertension referral pathway. It records actions performed by authenticated organisations and staff; it does not diagnose, prescribe or make clinical decisions. It treats the event ledger as the history of record and ordinary status columns as queryable projections.

## Actors and authority

| Actor | Allowed responsibilities |
|---|---|
| Administrator | Create organisations, provision staff, audit all patient chains, review cross-organisation metrics |
| Pharmacy / PMV | Record screening for its own organisation, create referral from its own positive screening, read its own referral thread, record assigned follow-up measurements |
| Hospital | See its own incoming queue, accept/decline/redirect a referral, book/rebook appointments, attest attendance, record missed/unreachable events, acknowledge emergency flags |
| Clinician | See assigned facility queue, submit disposition only for an encounter assigned to that clinician, schedule follow-up |
| Patient | Access their own receipt/notifications, acknowledge their receipt, decline their own referral, request reschedule and revoke their consent |
| HMO | Read operational referral metrics; no patient-level event payload export from the metrics endpoint |

The acting identity and role come from the verified bearer token and current database record. Request bodies do not contain trusted `actor_id` or `actor_role` values. Organisation membership is checked in the service layer for every operational action.

## State model

### Positive-screen canonical path

```text
SCREEN_POSITIVE
  -> REFERRAL_CREATED
  -> FACILITY_ACCEPTED
  -> APPOINTMENT_BOOKED
  -> CLINICAL_ENCOUNTER_COMPLETED
  -> CLINICAL_DISPOSITION_RETURNED
  -> FOLLOWUP_DUE
  -> REPEAT_ASSESSMENT
  -> BP_CONTROL_RECORDED
  -> FOLLOWUP_DUE ...
```

A negative screen is recorded as `SCREEN_NEGATIVE`; an inconclusive screen is recorded as `SCREENING_INCONCLUSIVE`. Neither starts a referral. A new episode for the same patient can begin only after an allowed terminal or recoverable state. Re-screening cannot be used to bypass an active referral or appointment.

### Failure and recovery path

Supported failure events include `REFERRAL_DECLINED`, `FACILITY_UNAVAILABLE`, `REFERRAL_REDIRECTED`, `APPOINTMENT_MISSED`, `PATIENT_UNREACHABLE`, `PATIENT_DECLINED`, `PATIENT_REQUESTED_RESCHEDULE` and `FOLLOWUP_OVERDUE`.

- A receiving hospital can decline an incoming referral. If it specifies another facility, the decline, new referral, fresh SLA window, explicitly unknown eligibility placeholder and redirect event are committed in the same transaction.
- A hospital can mark an appointment missed. Rebooking creates a new appointment record and event; the previous booking is not overwritten.
- A patient can request a reschedule or decline their own referral using their patient token.
- A clinician can schedule a follow-up. A pharmacy/PMV can record a repeat BP assessment and a BP-control observation when the current state allows it.

Every transition checks the current state, target state, actor role, required payload and date/measurement invariants. The state check, domain write and ledger append use the same database transaction; an exception causes the request transaction to roll back.

## Endpoint groups

API prefix: `/api/v1`.

### Identity and organisations

- `POST /auth/register`: patient-only self-registration. A caller cannot choose a staff or administrator role.
- `POST /auth/login`, `GET /auth/me`: issue and inspect short-lived bearer credentials. Role and active status are re-read from the database.
- `POST /auth/provision`: administrator-only staff creation. Role must match an existing organisation type; `clinician` is attached to a hospital organisation.
- `POST /organisations`: administrator-only organisation creation.

### Screening and referral

- `POST /screenings`: pharmacy/PMV creates or reuses a patient by phone lookup, stores consent, validates BP, classifies positive/negative and red-flag status, encrypts measurements, and appends the screening event.
- `POST /referrals`: pharmacy/PMV can refer only a positive screening created by its own organisation. Active referral consent is required. Receiving organisation must be a hospital.
- `GET /referrals/{id}/history`: only members of the referring or receiving organisation, plus an administrator, may inspect the referral's event history. Patient clinical payloads are decrypted only while the patient's data key remains available.

### Hospital and clinician

- `GET /hospital/queue`: hospital users see referrals for their own facility; administrators and facility clinicians have their defined views.
- `POST /hospital/referrals/{id}/accept` and `/decline`: hospital acceptance or decline; optional redirect creates a linked referral rather than mutating old events.
- `POST /hospital/referrals/{id}/appointments`: book or rebook with timezone-aware timestamps and a positive duration.
- `POST /hospital/referrals/{id}/appointments/missed` and `/unreachable`: record failure events.
- `POST /hospital/referrals/{id}/attendance`: hospital attests attendance and identifies an active clinician at that same facility. Notes are encrypted.
- `POST /hospital/referrals/{id}/disposition`: only the clinician assigned to the recorded encounter can return the outcome and next step. Both are encrypted at rest and in the patient ledger payload.

### Patient portal and privacy

- `POST /patients/otp/request`: generic response to avoid exposing whether a phone number exists. One-time codes expire and have a bounded attempt count. No external delivery provider is connected yet.
- `POST /patients/otp/verify`: verifies the one-time code and returns a patient bearer token. `development_code` is only returned in development/test settings.
- `GET /patients/me/receipt`: patient reads their own event thread and verification result. The patient identity is taken from the token, not from a query parameter.
- `POST /patients/me/receipt/acknowledge`: appends `PATIENT_ACKNOWLEDGED`.
- `POST /patients/me/referrals/{id}/decline` and `/reschedule-request`: patient-owned failure/recovery events.
- `POST /patients/{id}/consent/revoke`: patient or administrator revokes active consent. Patient data key is shredded, the contact lookup hash is rotated, patient account is disabled and email ciphertext is cleared. The revocation event itself is appended before the account is disabled. Old clinical payloads remain hash-verifiable but cannot be decrypted through the application.

### Follow-up, communications and FHIR

- `GET/POST /patients/{id}/followups`, `/assessment`, `/bp-control`: clinician schedules; assigned pharmacy/PMV records repeat measurements and control status. A human must call these endpoints; there is no timer/worker.
- `GET /red-flags` and `POST /red-flags/{id}/acknowledge`: view and acknowledge recorded red-flag alerts. `dispatch_enabled` is always false.
- `POST/GET /referrals/{id}/messages`: encrypted care-team consultation thread, restricted to the referral's care organisations.
- `GET /patients/me/notifications`: patient's notification history; message bodies are encrypted.
- `GET /fhir/metadata`, `GET /fhir/patients/{id}/bundle`: authenticated FHIR R4 metadata and export for a patient the actor is authorised to access. Export intentionally omits direct identifiers.
- `GET /metrics`: administrator/HMO operational aggregates. Financial value is `null` until a real payer contract defines a defensible unit value.

## Data protection implementation

- Patient phone values are AES-GCM encrypted using a per-patient data key. A separate keyed HMAC index supports lookup without storing the number in clear text.
- Display name, age band, insurance metadata, BP values, symptoms, event payloads, encounter notes, disposition text, red-flag notes, messages and notification bodies are stored as ciphertext or redacted digests.
- Patient data keys are wrapped with the dedicated PII encryption key. Consent revocation destroys the wrapped key, rotates phone lookup values, and removes encrypted account email for linked patient accounts.
- Account emails are encrypted with the PII key and indexed using a keyed digest. Old pre-v2 plaintext email records are upgraded on successful login because an Alembic migration cannot safely encrypt them without the deployment's secret key.
- Event digests commit to the event fields, previous event hash and actor public key. Ed25519 signatures are independently verifiable using the stored actor public key.

Data encryption at rest does not replace TLS, managed key custody, access review, backups, legal basis, retention controls or a breach response process.

## Explicit simulation boundaries

| Component | Current behaviour | Not implemented |
|---|---|---|
| Eligibility | Local record with `decision=unknown` and simulated adapter marker | Live NHIA/DHIN coverage check or benefit confirmation |
| SMS/WhatsApp | Records a simulated notification; no provider call | Live delivery, delivery receipt or inbound SMS webhook |
| OTP | Generates and verifies a one-time code; development/test response may reveal code | Production SMS/voice delivery provider |
| Emergency alert | Records a red-flag exception and acknowledgement | Paging, ambulance dispatch, emergency-response SLA or escalation centre |
| Follow-up | Persists due dates and manual follow-up transitions; overdue referral exceptions are generated by `python -m app.cli escalate-overdue` when invoked by an external scheduler | In-process background worker, automatic patient reminder, emergency paging or automatic clinical-state transition |
| FHIR | Authenticated R4 collection bundle export | Full FHIR server, search/create/update interaction or conformance certification |
| Claims/finance | Returns operational data and no financial value estimate | Live claims, reimbursement, payer settlement or ROI guarantee |

No code path should present a simulated action as a completed external integration.

## Validation

Run:

```powershell
python -m pytest -q
alembic upgrade head
```

Integration tests exercise the successful journey, failure transitions, referral redirection, appointment rebooking, access boundaries, consent revocation, event-chain verification, FHIR export and encrypted-at-rest checks.

### Confirmatory assessment and ownership

- `POST /hospital/referrals/{id}/confirmatory-assessment`: after attendance is recorded, only the clinician assigned to that encounter can document a confirmatory method: repeat office measurement, home monitoring, ambulatory monitoring, or `not_indicated` with a written reason. It is a clinician-entered record, not an automated diagnostic decision. A disposition is blocked until this step is recorded.
- `POST /hospital/referrals/{id}/assign`: an administrator or the receiving hospital can assign/reassign an active referral to an active hospital staff member or clinician at that same facility. The assignment is recorded as an auxiliary signed ledger event.
- New referrals are unassigned until accepted. Acceptance assigns the receiving hospital user; attendance assigns the encounter to the selected clinician. Clinician worklists show only referrals assigned to that clinician.
- `POST /hospital/referrals/{id}/redirect`: a declined or unavailable referral can be redirected later if the original decline did not include an alternative facility. The prior failed attempt remains in the ledger and the receiving facility gets a new referral record with a fresh SLA window.
- `GET /hospital/attention`: shows open SLA exceptions and active referrals without an owner, scoped to the administrator or receiving hospital.
- `python -m app.cli escalate-overdue`: scans active referrals past their SLA and creates one idempotent operational exception per referral. It does not move a patient through a clinical state or claim that an external person was paged. Configure this command in a managed scheduler/cron/Windows Task Scheduler for recurring execution; no background scheduler runs inside the web process.

The event ledger distinguishes workflow-state events from supplementary events such as messages, patient acknowledgements, consent changes, confirmatory records and ownership assignments. Only recognised domain states determine the next legal transition. Supplementary events remain in the chronological, signed history but do not replace the patient's current care state.
