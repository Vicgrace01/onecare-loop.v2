# Security design and remaining risks

## Controls implemented in this prototype

- Argon2id password hashing; short-lived signed bearer tokens.
- Current role and account-active status are reloaded from the database for each authenticated request.
- Public registration creates only patient-role accounts. Staff provisioning is administrator-only and organisation-type constrained.
- Care actions derive the actor from the bearer token. Hospital, pharmacy/PMV and clinician operations are scoped to the assigned organisation and referral.
- Patient phone, display name, demographics, BP measurements, symptoms, ledger payloads, encounter notes, disposition text, case messages, alert notes and notification bodies are encrypted at rest with patient-scoped data keys.
- Account email addresses are encrypted using the dedicated PII key; a keyed lookup token replaces cleartext email in indexed columns. Legacy pre-v2 email records are migrated to encrypted form on successful login.
- Patient data keys are wrapped with a PII key separate from the event-signing master key. Consent revocation destroys the wrapped patient key, rotates phone lookup values, disables the linked patient account and clears account email ciphertext.
- AES-GCM authenticated encryption is used for protected fields and payloads.
- Ledger events form a per-patient SHA-256 chain. Ed25519 signatures are made over the event digest; the actor public key is committed into the digest. Verification detects hash, ordering, signature and head mismatches.
- State validation, related care-record mutations and ledger appends share a request transaction.
- Alembic migrations are separate from production application startup. Production configuration rejects auto schema creation and demo-admin seeding.
- SQLAlchemy foreign keys and database check constraints cover core roles and domain values.

## Trust-boundary limitations

The current event-signing service is application-controlled. Private signing material is encrypted at rest, but a compromised running application with its master key can still produce signatures. These signatures provide verifiable integrity/accountability within the prototype; they are not non-repudiation proof that a particular human personally approved a clinical decision. Production should move signing to KMS/HSM-backed or actor-controlled keys and anchor ledger heads externally.

The patient PII encryption design is application-mediated. A compromised application process with the PII key can decrypt stored records for a patient whose key has not been shredded. Key rotation, recovery and escrow procedures must be designed before a real pilot.

Old pre-v2 plaintext account email values cannot be encrypted by an offline migration because the deployment secret is unavailable to Alembic. They are upgraded at successful login. An existing deployment must identify and handle dormant legacy accounts before migrating actual patient data.

## Not yet implemented / production blockers

1. **Independent key custody:** KMS/HSM integration, key rotation, break-glass governance, access logging and audited recovery.
2. **External ledger anchoring:** periodic ledger-head signatures/timestamps stored outside the primary database and tested disaster recovery.
3. **Abuse protection:** edge and application rate limits, IP/device abuse monitoring, login lockout policy, bot controls and alerting. OTP has expiry and per-code attempt limits, but no full abuse-control stack.
4. **Session lifecycle:** staff MFA, password reset/recovery, session revocation and refresh-token/device management.
5. **Production operations:** PostgreSQL deployment validation, TLS, encrypted backups, tested restore, availability monitoring, log redaction, incident response and least-privilege database access.
6. **Privacy and legal controls:** independent DPIA, lawful-basis and consent review, retention/deletion schedule, data subject request process, breach playbook and NDPA counsel review.
7. **Data residency/vendor assessment:** hosting region, cross-border safeguards, subprocessors, SMS provider contracts and transfer agreements must be validated before a Nigerian pilot.
8. **Clinical review:** licensed-provider review of measurement thresholds, escalation language, workflow responsibilities, user training and safety monitoring.
9. **Live integrations:** NHIA/DHIN eligibility, SMS/WhatsApp, claims/reimbursement and emergency response require real provider agreements and integration tests. Current adapters are simulated or absent.
10. **Frontend protections:** the current API uses bearer authentication and no cookie-based sessions. If a browser UI later stores auth in cookies, add CSRF protections, secure cookie policy and appropriate CSP/XSS controls.

## Explicit non-claims

- A hash chain is not a blockchain and is not tamper-proof against an administrator who controls the database and signing keys.
- Encrypted at rest does not mean automatically NDPA-compliant.
- BP screening thresholds do not diagnose a patient or determine treatment.
- A logged red flag is not an ambulance dispatch or emergency response.
- Simulated notification/eligibility records are not proof of external delivery or coverage.
- Passing an automated test suite does not constitute clinical validation, regulatory approval, penetration testing or production readiness.

This is an engineering prototype. Do not use it to process real patient data until the remaining controls have been reviewed and approved.
