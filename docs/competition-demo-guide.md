# Judge demonstration — OneCare Loop v2

## What a judge sees

Open `/` and choose **Watch the full automatic demo**, or open `/demo` directly.

The page has one primary action: **Start full demo**. It calls `POST /api/v1/demo/run`, which creates a new synthetic case by calling the same application services used by the authenticated pharmacy, hospital and clinician APIs. The response contains the recorded event sequence and a chain-verification result. The browser then choreographs those persisted events across the pharmacy, hospital, patient and clinician panels.

This is not a hard-coded front-end animation: the screening, referral, acceptance, appointment, attendance, confirmatory assessment, disposition, follow-up plan and signed events are created in the FastAPI database. The visual sequence is a replay of the recorded result after the service transaction completes; it is not a real-time animation of each database write.

**Replay animation** reuses the previous response. It does not create another patient or add duplicate events. **Start full demo** creates a fresh synthetic case.

## What the demo demonstrates

1. A community pharmacy records a consented positive blood-pressure screening.
2. A referral is opened with its urgency and SLA deadline.
3. The receiving hospital accepts it and becomes the accountable owner.
4. An appointment is created and a simulated notification record is stored.
5. Attendance is attested against the receiving hospital's assigned clinician.
6. The assigned clinician records a repeat-office confirmatory assessment.
7. The clinician returns a disposition and a documented next step.
8. A 30-day follow-up plan is scheduled.
9. The patient event chain is checked for sequence, hash and signature integrity.

The ring presents six principal workflow milestones. The event timeline also shows supplementary steps, including the confirmatory assessment and follow-up scheduling.

## Fastest local judge setup

The project includes `.env.judge.example` with four intentionally public, synthetic-only test accounts. In PowerShell, from the project root:

```powershell
Copy-Item .env.judge.example .env
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` and select **Watch the full automatic demo**, or open `http://127.0.0.1:8000/demo` directly. The demo page displays these four role credentials because `DEMO_SHOW_CREDENTIALS=true` is enabled in the judge example file.

| Role | Login email | Public judge-demo password |
|---|---|---|
| Pharmacy | `demo.pharmacy@onecareloop.com` | `Demo-Pharmacy-2026-OneCare!` |
| Hospital | `demo.hospital@onecareloop.com` | `Demo-Hospital-2026-OneCare!` |
| Clinician | `demo.clinician@onecareloop.com` | `Demo-Clinician-2026-OneCare!` |
| HMO reviewer | `demo.hmo@onecareloop.com` | `Demo-HMO-2026-OneCare!` |

These are deliberately public evaluation accounts, not secure personal accounts. The judge example uses the separate `onecare-judge-demo.db` database and disables patient self-registration. Replace the three local-only application keys before hosting anywhere, keep this database synthetic-only, and never reuse the demo passwords. The deployment's environment variables—not the committed HTML—are the source of the credential values displayed by the page.

## Required environment configuration

The judge demo is disabled by default in `.env.example`. Enable it only in a **dedicated synthetic-data deployment and database**. Do not turn it on in a database containing real patient information. For hosted judging, copy the settings below into the host's environment configuration and replace the three local-only application keys with distinct random values:

```dotenv
DEMO_MODE_ENABLED=true
DEMO_SHOW_CREDENTIALS=true
DEMO_PHARMACY_EMAIL=demo.pharmacy@onecareloop.com
DEMO_PHARMACY_PASSWORD=<unique-password-at-least-12-characters>
DEMO_HOSPITAL_EMAIL=demo.hospital@onecareloop.com
DEMO_HOSPITAL_PASSWORD=<different-unique-password>
DEMO_CLINICIAN_EMAIL=demo.clinician@onecareloop.com
DEMO_CLINICIAN_PASSWORD=<different-unique-password>
DEMO_HMO_EMAIL=demo.hmo@onecareloop.com
DEMO_HMO_PASSWORD=<different-unique-password>
```

All four passwords must be at least 12 characters and different. Generate a separate strong value for each account, for example with this PowerShell command:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

The startup routine creates or refreshes four organisation-scoped staff accounts:

| Workspace | Role | Purpose |
|---|---|---|
| Community pharmacy | `pharmacy` | Screen and initiate referrals |
| Hospital coordinator | `hospital` | Accept and manage incoming referrals |
| Assigned clinician | `clinician` | Record confirmatory assessment and disposition |
| HMO reviewer | `hmo` | Review aggregate operational metrics |

The page retrieves their emails and, only when `DEMO_SHOW_CREDENTIALS=true`, their passwords from `GET /api/v1/demo/info`. Credentials are not hard-coded into HTML or JavaScript. A judge can use them from the homepage's **Sign in securely** screen. The patient is generated for each run; it is not a staff login.

For an environment where the reviewer page should not display passwords, set `DEMO_SHOW_CREDENTIALS=false`. The role accounts remain available to the deployment operator, but the public page shows only the email addresses and an instruction to use the private credential handoff.

After setting environment variables, restart the application. In production-like deployments, run the normal Alembic migration command before starting the service. Demo account provisioning happens during application startup.

## Honest demo boundaries

- Patient, pharmacy, hospital, clinician and care data created by the demo are synthetic.
- The generated case is persisted in the configured demo database. Repeated starts create separate synthetic cases; replay does not.
- Notifications are written as simulated notification records. **No SMS or WhatsApp message is sent.**
- Eligibility is recorded as `unknown`. There is no live NHIA/DHIN query.
- A synthetic clinician actor records the confirmatory assessment and disposition. This is not a real clinical consultation or an endorsement of the selected reading.
- No financial savings, reimbursement, clinical outcome improvement or patient adherence claim is calculated by this demo.
- The demo endpoint is public only when enabled. It has a per-process limit of five runs per client IP per hour. A multi-worker public deployment should add a shared edge or datastore-backed rate limit.
- `/demo` remains available when the demo is disabled so that the page can explain the state. `GET /api/v1/demo/info` reports `enabled=false`; `POST /api/v1/demo/run` returns 404.

## Judge walkthrough

1. Open the homepage and select **Watch the full automatic demo**.
2. Check the synthetic-data disclosure and the four reviewer roles.
3. Select **Start full demo** and watch the journey ring, organisation panels, patient updates and event timeline.
4. Confirm that the clinician panel shows the repeat-office confirmatory assessment before the returned disposition.
5. Confirm that follow-up has a due date and the chain reports **VERIFIED**.
6. Select **Replay animation**. It should replay the same eight recorded events without making another API call.
7. Return to the homepage, sign in as the pharmacy, hospital, clinician or HMO reviewer and inspect the role-limited workspace.

## Troubleshooting

- **Demo not enabled:** set `DEMO_MODE_ENABLED=true` and restart.
- **Demo credentials missing:** check that all four distinct passwords meet the minimum length and the matching environment variables are visible to the service.
- **Account provisioning conflict:** check whether one of the configured demo email addresses is already assigned to another role or organisation. Use dedicated demo email addresses and a dedicated demo database.
- **Chain verification failure:** preserve the returned run reference and inspect the database/service logs. Do not manually edit or delete the event rows.
- **Replay disabled:** replay is enabled only after a successful run.

The endpoint is an evaluator convenience for the synthetic prototype. It is not a patient-facing production API or a substitute for staff authentication and organisation-level authorization in the operational APIs.
