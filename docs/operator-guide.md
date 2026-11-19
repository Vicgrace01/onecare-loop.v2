# OneCare Loop operator guide

## First local run

1. Install Python 3.11 or newer.
2. Create and activate `.venv`.
3. Install `requirements.txt`.
4. Copy `.env.example` to `.env` and generate distinct `SECRET_KEY`, `SIGNING_MASTER_KEY` and `PII_ENCRYPTION_KEY` values.
5. For the local demonstration only, set `APP_ENV=development`, `SEED_DEMO_ADMIN=true`, and a `DEMO_ADMIN_PASSWORD` of at least 12 characters. Restart the server once to seed the admin; or leave demo seeding off and use `python -m app.cli create-admin`.
6. Run `alembic upgrade head`, then `uvicorn app.main:app --reload`.
7. Open `http://127.0.0.1:8000`.

## Create the care network

Sign in as administrator. Under **Organisations & staff**, create at least one pharmacy/PMV and one hospital. Provision separate staff accounts for the correct organisation type. A clinician is assigned to a hospital organisation. Staff sign in using the email and temporary password set by the administrator.

## Complete a workflow

- Pharmacy/PMV: record patient contact and screening details; tick the consent confirmation; choose a registered receiving hospital; submit.
- Hospital: accept the referral; book a timezone-aware appointment; after the visit select the assigned clinician and attest attendance.
- Clinician: sign in and open the clinical review worklist; return the clinician-documented disposition; schedule the next follow-up.
- Pharmacy/PMV: record repeat BP assessment and BP-control status when due.
- Patient: use the phone OTP portal. In development/test the code is shown as `development_code`; this field is never returned in production. Review the receipt and acknowledge it.

## Role controls

- Public signup can create patient accounts only.
- Administrators create organisations and provision staff accounts.
- Pharmacy/PMV accounts are limited to screenings created by their own organisation.
- Hospital and clinician accounts are limited to referrals routed to their assigned hospital.
- Clinician disposition is checked against the clinician assigned to the encounter.
- Patient tokens can access only the patient's own receipt, notification and follow-up resources.

## Current service boundaries

SMS/WhatsApp, NHIA/DHIN coverage, claims payment and emergency dispatch are not connected. Notification records are marked simulated; eligibility remains unknown unless a verified external adapter is implemented. Follow-up plans are stored but no background scheduler sends reminders. Do not enter real patient data in this prototype before clinical, security and regulatory readiness review.

## Confirmatory review, ownership and SLA operations

1. A hospital accepts a referral. The accepting hospital account becomes the initial responsible owner.
2. When attendance is attested, the hospital selects an active clinician at its own facility. That clinician becomes the referral owner and receives the clinical work item.
3. The assigned clinician records a confirmatory assessment (repeat office reading, home monitoring, ambulatory monitoring, or a documented reason why confirmation is not indicated). The clinical disposition remains blocked until this record exists.
4. The clinician returns the disposition and documented next step. The referral is then closed in the workflow and a follow-up plan can be created.
5. Hospital operators can reassign active referrals to another staff member at their facility. If a referral is declined without being redirected immediately, select an alternative receiving hospital and use the redirect action; the original decline remains in the history.
6. The queue highlights unassigned work and SLA breaches. The **Operational attention** panel lists open overdue exceptions and unassigned referrals.

### Run SLA escalation

The application does not run a background scheduler. Configure this command in a scheduler appropriate to the deployment:

```powershell
python -m app.cli escalate-overdue
```

It is safe to run repeatedly: each referral receives at most one `REFERRAL_SLA_BREACHED` operational exception. The exception is an operational database record, not a signed clinical event, and it does not page a care navigator or emergency responder. A human operator must review and action the exception. For a recurring run, use a managed job scheduler or Windows Task Scheduler with the same application environment and database credentials.
