# OneCare Loop v2 — judge-ready prototype release

## Main changes

- Retains the modular FastAPI architecture rather than merging legacy Flask routes into the new service.
- Fixes canonical workflow state so consultation, acknowledgement, consent and other supplementary ledger events cannot corrupt the state machine.
- Adds an explicit clinician-entered confirmatory assessment gate before clinical disposition.
- Adds named referral ownership, facility-scoped reassignment, assigned-clinician worklists and idempotent overdue-SLA exception processing.
- Adds late referral redirection with a fresh SLA and explicit unknown/simulated eligibility state.
- Extends supported FHIR export to include confirmatory BP observations.
- Restores the original visual identity and motion language using CSS/native JavaScript: ambient particle canvas, scroll reveals, staged six-node animation, metric count-ups, ripple feedback, desktop cursor, magnetic buttons and transitions.

## New one-click judge demonstration

- Homepage CTA links to `/demo`, with a dedicated guided reviewer page.
- One click calls the FastAPI demo endpoint and creates a synthetic care case through the same application service layer.
- The page choreographs the six-stage loop across pharmacy, hospital, patient and clinician panels; the timeline shows eight persisted/signed events.
- It displays the confirmatory reading, clinician disposition, follow-up due date and chain verification result.
- Replay does not call the API again and does not create duplicate records.
- `deploy/judge-demo.env.example` provides a local synthetic-only configuration with placeholders. Operators must replace all application keys and demo passwords before use. Credentials are loaded from runtime configuration and shown only when `DEMO_SHOW_CREDENTIALS=true`.
- The endpoint is synthetic-only, rate-limited per process and transparent about simulated messaging, unknown eligibility and the absence of real outcome/savings claims.

## Validation

On 19 November 2026, all **46 collected tests passed in three separate runs**: 41 non-browser tests, 4 existing browser tests and 1 judge-demo browser test. The monolithic pytest run intermittently stalled when multiple Playwright sessions shared a process; this is disclosed rather than presented as a single-run pass. Python compilation, JavaScript syntax and a fresh SQLite Alembic upgrade/downgrade/re-upgrade check passed. Ruff and Docker were unavailable and are not claimed as passed. See `BUILD_STATUS.md`.

## Boundaries

Live NHIA/DHIN, SMS/WhatsApp, claims and emergency dispatch remain unconnected. SLA exception processing requires an external scheduler. The FHIR export is not a certified FHIR server. No clinic pilot or real-world outcome evidence has been collected. Judge credentials are configured at runtime and must only be exposed in a dedicated synthetic-data environment.
