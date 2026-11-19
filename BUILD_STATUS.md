# OneCare Loop v2 — release validation record

## Architecture and scope

- [x] Modular FastAPI monolith with SQLAlchemy 2, Pydantic 2 and Alembic.
- [x] Argon2id password hashing, signed bearer tokens and database-backed role checks.
- [x] Organisation-scoped staff permissions and patient-scoped records.
- [x] Signed, hash-chained event history with tamper verification.
- [x] Atomic care transitions and explicit separation of workflow-state events from supplementary ledger events.
- [x] Encrypted patient contact/clinical data and account-email storage; consent revocation and key shredding flows.
- [x] Responsive same-origin web interface served by FastAPI.
- [x] Original OneCare visual identity adapted to FastAPI: navy/teal/peach palette, typography, animated six-stage loop, split sign-in and patient journey ring.
- [x] Native CSS/JavaScript motion: ambient particles, scroll reveals, staggered cards, ripple feedback, metric counters, desktop cursor, magnetic CTAs and page transitions.
- [x] Touch and reduced-motion fallbacks; old Flask routes/templates and GSAP/ScrollTrigger/Lenis runtime are not imported.

## Care workflow capabilities

- [x] Positive, negative and inconclusive BP screening with consent capture.
- [x] Referral creation with explicitly unknown/simulated eligibility where no live payer query exists.
- [x] Hospital acceptance/decline, appointment booking/rebooking, attendance and clinician disposition.
- [x] Clinician-entered confirmatory assessment or documented `not_indicated` decision before disposition.
- [x] Named referral ownership, facility-scoped reassignment and assigned-clinician worklists.
- [x] Patient acknowledgement, care-team consultation messages and patient receipt.
- [x] Late referral redirection with a new referral identifier and fresh SLA.
- [x] Idempotent SLA exception processor and overdue/unassigned attention view.
- [x] Follow-up plans, repeat assessments and BP-control events.
- [x] Authenticated FHIR R4 collection export for supported resources.

## Judge demo

- [x] Homepage CTA links to `/demo`; the page is also directly addressable.
- [x] One-click API run creates a synthetic case through the actual FastAPI service functions.
- [x] Choreographed six-stage ring and four role panels display eight persisted, signed events.
- [x] Clinician confirmatory assessment is shown before disposition; 30-day follow-up is visible.
- [x] Replay reuses the previous result and does not create duplicate patients/events.
- [x] Chain verification status and transparent limits are shown.
- [x] Dedicated `.env.judge.example` provides a separate synthetic-only database and four public test accounts. Credentials are dynamically returned by the API only when `DEMO_SHOW_CREDENTIALS=true`.
- [x] Demo is disabled by default in `.env.example`; public demo endpoint has a per-process rate limit and no live SMS/WhatsApp or payer integration.

## Final verification (19 November 2026)

Test groups were run separately because combined runs with multiple Playwright browser sessions intermittently stalled in this execution environment. Every collected test passed in one of the three runs:

- **41 non-browser tests passed**: `python -m pytest -q --ignore=tests/test_browser_e2e.py --ignore=tests/test_judge_demo_browser.py`.
- **4 application browser tests passed**: `python -m pytest -q tests/test_browser_e2e.py`.
- **1 judge-demo browser test passed**: `python -m pytest -q tests/test_judge_demo_browser.py`.
- **46 tests total passed across those three runs**. The tests include sign-in for each of the four judge accounts, the full eight-event demo workflow, chain verification, replay without duplicate API calls, role credential visibility, mobile/reduced-motion handling and workflow UI regression checks.
- `python -m compileall -q app tests migrations` passed.
- `node --check app/web/assets/js/app.js`, `node --check app/web/assets/js/heritage-motion.js` and `node --check app/web/assets/js/demo.js` passed.
- Fresh SQLite Alembic `upgrade head` → `downgrade -1` → `upgrade head` passed.
- Ruff was unavailable; no Ruff result is claimed. Docker was unavailable; a local image build was not run.

## Explicitly not live / not production-approved

- No live NHIA/DHIN eligibility query, SMS/WhatsApp/voice provider, claims settlement or emergency dispatch.
- SLA exception processing requires an external scheduler to invoke the CLI; no background worker pages coordinators.
- Follow-up reminders and transitions require authenticated user actions.
- FHIR support is an authenticated R4 collection export, not a full FHIR server or conformance certification.
- The judge demo is synthetic. Notifications are simulated records; it calls no external messaging provider. Metrics are not evidence of improved real-world outcomes.
- The judge example passwords are intentionally public and must be confined to the synthetic demo deployment. Do not reuse them or use this configuration with real patient information.
- This remains an engineering prototype. Do not use with real patient data before independent security, privacy, legal, clinical and operational review.

## Pre-pilot work still required

Independent penetration test; KMS/HSM-backed key custody; external ledger anchoring; production PostgreSQL operations and tested backup/restore; shared rate limiting and abuse monitoring; TLS and residency/vendor review; incident response and retention processes; NDPA legal review; licensed-clinician protocol validation; local-language review; live provider agreements; usability testing and a supervised pilot.
