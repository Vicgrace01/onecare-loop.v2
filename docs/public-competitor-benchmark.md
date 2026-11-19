# Public competitor benchmark — Future Health Challenge 05

**Evidence cut-off: 19 November 2026.** This is a public-evidence benchmark, not an official competition ranking.

## Scope and caveat

The official challenge page describes prototype submission by 20 November 2026 and expert evaluation from 20–30 November, and lists impact/clinical relevance, technical architecture, working prototype/demo, safety/data governance, scale/deployment and commercial/pilot potential as assessment dimensions. It does not publish a complete public list of all entrants or their submissions. Consequently, it is not possible to identify or score **everyone who applied** from public material. This review covers the identifiable public projects that explicitly describe themselves as responses to the *Closing the Screening-to-Care Loop* statement, plus OneCare Loop. A public project page or a GitHub repository is not proof that the organiser accepted an entry. No judging results or private scores are known.

The GitHub trees were enumerated recursively where public repositories existed. We read the READMEs and inspected selected workflow, engine, interoperability, security, test and demo files. We did **not** run competitor code, reproduce author-reported benchmarks, inspect non-public source, or audit every line of every competitor repository. Scores describe the evidence visible to a reviewer, not the intrinsic quality of software that was not available to inspect.

Official challenge assessment headings include health impact and clinical relevance, technical depth and architecture, working solution and demonstration quality, responsible AI/safety/data governance, scalability/deployment readiness and commercial/pilot potential. The weighted rubric below is our comparative interpretation of those headings, not the organiser's internal formula.

## Weighted rubric

| Dimension | Weight | What earns a high score |
|---|---:|---|
| Workflow completeness and clinical relevance | 25% | Result communication and understanding, confirmation, referral, acceptance, attendance, care plan and documented closure; explicit failure recovery |
| Technical architecture and integrity | 20% | Inspectable implementation, coherent state model, authorization, persistence/transactions, audit integrity and maintainable structure |
| Patient experience, ownership and escalation | 15% | Named owners, due dates, actionable worklists, patient communication/acknowledgement and human escalation |
| Interoperability | 10% | Grounded FHIR/HL7 mapping, import/export, validator or round-trip evidence |
| Validation and evidence | 15% | Reproducible tests, workflow coverage, falsifiable assumptions, independent or well-documented technical evidence |
| Judge/demo readiness | 10% | Publicly accessible, resettable, guided, role-aware or one-click end-to-end demonstration |
| Scale and path to pilot | 5% | Deployment architecture, operational controls and a credible, bounded pilot plan |

A score is rounded to one decimal place. Confidence refers to how much source code and primary evidence was inspectable, not confidence in a future competition result.

## Scorecard

| Project | Workflow /10 | Architecture /10 | Ownership & patient experience /10 | Interop /10 | Validation /10 | Demo /10 | Pilot path /10 | Weighted score | Evidence confidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Loop Closer — DesignMaster Solutions** | 9.4 | 7.8 | 9.3 | 9.8 | 9.0 | 9.5 | 6.2 | **8.9** | High |
| **LoopShield — Agnuxo1** | 9.1 | 8.6 | 9.0 | 7.6 | 9.4 | 9.5 | 7.4 | **8.8** | High |
| **CareLoop — ossolola** | 8.4 | 8.2 | 8.0 | 6.8 | 8.2 | 7.9 | 7.4 | **8.0** | Medium |
| **OneCare Loop — FastAPI v2 candidate** | 8.1 | 8.5 | 7.8 | 6.7 | 7.2 | 8.8 | 7.2 | **7.9** | High for the local source package; not yet reflected on public `main` |
| **CareTrack — HIMForward** | 8.7 | 6.5 | 9.0 | 7.0 | 6.2 | 9.4 | 6.9 | **7.7** | Medium-low; public demo and technical docs, no source repo audited |
| **CareLoop — SOLIFAN / solidfdn** | 8.2 | 6.5 | 8.2 | 7.5 | 7.6 | 8.6 | 7.0 | **7.7** | Low-medium; public demo/docs, implementation absent from repo |
| **Lupora** | 7.8 | 5.5 | 8.0 | 5.5 | 5.0 | 6.8 | 6.8 | **6.6** | Low; website-level evidence |
| **LoopCloser — OLL4** | 7.0 | 5.3 | 7.0 | 5.3 | 4.7 | 6.0 | 7.5 | **6.1** | Low; website-level evidence |
| **JahanZari — Screening-to-Care Loop** | 6.9 | 6.5 | 7.0 | 4.0 | 5.0 | 5.5 | 6.5 | **6.1** | Low; public site describes an Oracle APEX prototype, but demo login and no source repo prevent code audit |

These are deliberately not presented as exact predictions of judge scores. The apparent 0.1–0.3 differences are not meaningful where evidence depth differs. The most useful conclusions are the strengths and gaps by dimension, not the rank order.

## Repository structure and implementation comparison

Recursive public GitHub tree counts checked on 19 November 2026:

| Repository / project | Public tracked files | Observed structure | What the structure makes inspectable | Important caveat |
|---|---:|---|---|---|
| OneCare Loop FastAPI v2 candidate | 94 in the current local candidate (including judge-demo configuration and benchmark documents) | `app/api/v1`, `app/core`, `app/db`, `app/domain`, `app/schemas`, `app/services`, `app/web`, `migrations`, `tests`, `docs`, `deploy` | A conventional modular FastAPI monolith, SQLAlchemy models, explicit domain state/ledger, Alembic migrations, role-based web client and backend/browser tests | This version has not yet replaced the public Flask `main` branch; the judge must be given the correct new package/branch/deployment |
| Loop Closer — DesignMaster Solutions | 56 | `public` pure JS modules and static UI, `src/worker.mjs`, `test`, `scripts`, `docs/samples`, `video` | The core state machine and interoperability logic are shared pure modules, with node tests, HL7/FHIR samples and a Worker endpoint | README says public demo changes live in browser memory; no persistent case store or login |
| CareLoop — ossolola | 165 | `app`, `dashboard`, `db`, `rules`, `workflows`, `benchmark`, `data`, `docs` | Patient and coordinator pages, SQL/workflow definitions, benchmark fixtures and triage scripts | 129 of the 165 tracked files are JSON; many are data/fixtures rather than application modules. README says build in progress; self-reported benchmark/test numbers were not rerun |
| LoopShield — Agnuxo1 | 239 | `loopshield`, `sim`, `tests`, `bench`, `experiments`, `results`, `provenance`, extensive `docs` and demo assets | A Python case engine, pathway definitions, privacy gateway, FHIR export, tests, fuzz/simulation artifacts, evidence/provenance and browser demo | Many files are research/evidence assets and rendered media. Test, fuzz and privacy numbers are the author's reported results, not independently reproduced here |
| CareLoop — SOLIFAN / solidfdn | 33 | `assets`, `demo-data`, `docs`, `evidence`, README and notice | Architecture diagrams, demo guide, synthetic report fixtures, reviewer map and verification JSON | README explicitly says the application implementation is not included in this repository; source-level audit was not possible |
| CareTrack — HIMForward | No public source repository located | Public website, role-switching demo, guided stories and technical docs | Reviewer access, story-based walkthroughs, architecture and FHIR documentation | No inspectable code tree or source tests located |
| Lupora | No public source repository located | Public product/challenge website | Workflow narrative, owners, patient messaging, supervised AI and a proposed one-clinic pilot | No code repository or independently inspectable executable demo located |
| JahanZari — Screening-to-Care Loop | No public source repository located | Public Oracle APEX / Oracle Database prototype page; demo redirects to a login page | Case worklist, escalation queue, patient notice, role-based access and dashboard are described | No source tree or accessible reviewer demo credentials; code and workflow claims could not be verified |
| OLL4 LoopCloser | No public source repository located | Public product/challenge website | High-level description of fixed rules for overdue HbA1c follow-up and clinician-approved message drafting | No source tree, detailed test evidence or code-level demo located |

File count is not a quality metric. LoopShield's large tree contains experiments, results and rendered media; CareLoop ossolola's tree contains many JSON data fixtures; SOLIFAN's smaller tree is primarily documentation and evidence. Architecture and inspectable behaviour matter more than repository size.

## What each project appears to do best

### LoopShield — strongest documented operational controls and engineering evidence

The Python engine explicitly tracks a current owner and due time, escalates along an owner → care navigator → clinical lead ladder, handles urgent cases, missed appointments and rejected referrals, and blocks silent closure. It contains a privacy gateway designed to mask identifiers before optional message drafting, FHIR exports and a test/fuzz/research evidence structure. Its README reports 32 tests and 1.54 million processed events with zero invariant violations, but these results were not rerun for this review. The public demo and reviewer guide are unusually well-developed. Limitations remain: prototype on synthetic data, no clinic deployment, no live clinical integration and no proven outcome improvement.

### Loop Closer — strongest visible interoperability story

Its pure JS workflow model lays out nine explicit steps, including patient understanding and confirmatory testing, with per-step owners and SLA rules. It handles patient replies, consult requests, rejected referrals, missed-visit rebooking and evidence-backed clinician closure. `interop.mjs` accepts HL7 v2 ORU^R01 and FHIR DiagnosticReport/Observation inputs and emits FHIR R4 workflow resources. The repository includes validator and HAPI round-trip evidence. This is a strong judge-facing standards story. Its material weakness is persistence: the README says browser changes are kept only in memory and the public Worker endpoint stores nothing; it is not a persistent, logged-in operational case system.

### CareLoop — ossolola — strongest workflow-automation / data-fixture orientation

The README describes an n8n/Supabase/Postgres workflow, fixed rules for triage, patient/facility routing, reminders until booking/attendance, care-navigator escalation and a care-team dashboard. The repo includes SQL, n8n workflow code, a dashboard and benchmark fixtures. The project itself labels the build as in progress. Its stated test/benchmark outcomes should be treated as author-reported until independently reproduced. The FHIR language in the README is described as FHIR-shaped rather than a complete validated interoperability implementation.

### CareTrack — HIMForward — strongest guided role/story demonstration

Its public judge page and guided tour let reviewers explore role switching and several synthetic stories: completed loop, confirmatory testing, missed visit rescue, human override, surveillance and a patient question needing a person. Technical docs describe role boundaries, FHIR samples and what is built versus planned. The public demo says the header switches roles and there is no password. The source code is not public, so the underlying security, persistence, tests and backend architecture cannot be independently audited from a repository.

### CareLoop — SOLIFAN — strongest correction-aware evidence narrative

Its public documentation explains how a corrected report can invalidate affected confirmations while retaining the original decision and source evidence. It presents a source-linked record Q&A pattern and a human-governed evidence-review flow. The public repo contains architecture, demo instructions, validation/evidence artifacts and synthetic files, but the README says the application implementation is not published. This is a compelling product and governance story; technical implementation quality remains unverified.

### JahanZari — Oracle APEX prototype with limited inspectable evidence

The public site identifies itself as a Population Health Challenge 05 prototype, describes an Oracle APEX / Oracle Database implementation, and lists a case worklist, escalation queue, patient notice, role-based access and dashboard using generated cases. The public demo link opened a login page; no demo credentials or source repository were available during this review. Its score is therefore conservative and low-confidence: the feature story is relevant, but technical depth, operational validation and judge accessibility could not be inspected. [Project page](https://www.jahanzari.com/)

### Lupora and OLL4 — relevant public narratives, limited code evidence

Lupora describes a case register, next-step owners, patient communication and a small clinic pilot path. OLL4 describes deterministic/cited overdue HbA1c rules and clinician-approved patient messages. Both are relevant public challenge pages, but neither exposes enough source code or reproducible technical evidence to support a strong code-level score. Their lower scores reflect evidence visibility, not proof that the underlying private builds are poor.

## OneCare Loop v2 — strongest position and remaining gaps

### Strengths in this candidate

- A real FastAPI + SQLAlchemy + Alembic application, rather than a browser-only mock.
- Public staff registration is not allowed to choose elevated roles; staff provisioning and role checks are server-side.
- Facility-scoped operations and clinician encounter assignment are enforced by the service layer.
- Related workflow writes and signed ledger events use a shared SQLAlchemy request transaction.
- Patient PII and sensitive ledger payloads use patient-scoped encryption; account passwords use Argon2id.
- Supplementary events do not overwrite canonical care state.
- The confirmatory-assessment gate is required before clinical disposition.
- An accepting facility becomes the referral owner; attendance assigns the clinician; operational attention and owner reassignment are present.
- Follow-up is a separate due-dated plan. Referral and patient failure paths remain visible and recover through new events.
- The new one-click judge demo is linked from the homepage, creates a synthetic case through the actual service functions, animates the returned persisted event history, can display four intentionally public judge-only role credentials in a dedicated demo deployment and independently verifies the event chain. A ready-to-copy `.env.judge.example` is included. The candidate is not yet publicly deployed.

### Gaps versus the leaders

1. No HL7 v2 ORU ingestion. FHIR export exists, but validator and round-trip evidence are not yet at Loop Closer's level.
2. No real SMS/WhatsApp delivery, NHIA/DHIN eligibility, payer claims or emergency-dispatch integration.
3. Patient communications and acknowledgements are not yet as richly demonstrated as Loop Closer's interactive reply/consult pathway.
4. The public main branch is still the older Flask application. The FastAPI candidate must be published as a clearly identified branch or deployed build before asking judges to inspect the repository.
5. The demo is a synthetic end-to-end run and replay. It creates all service records within one API transaction and then animates their recorded sequence; it does not simulate independent external providers responding live.
6. No pilot, patient outcome, clinical effectiveness or real financial savings have been demonstrated.

## Priority actions before submission

1. Make the FastAPI candidate the exact code judges are sent to, not the old Flask `main` branch. Use a new branch or a dedicated repository; do not delete the original history.
2. Deploy the demo on a dedicated synthetic database. Enable `DEMO_MODE_ENABLED=true` and `DEMO_SHOW_CREDENTIALS=true` only there. Use distinct passwords and never reuse them elsewhere.
3. Run the full test suite from the final extracted ZIP and inspect test reports. Also run the deployed `/demo` path in a fresh browser and verify a run, replay, role login and chain check.
4. Keep the visible demo disclosure: no real SMS, no live eligibility, no live clinic integration, no real outcome claims.
5. Submit the repository URL, demo URL, judge credentials and limitations together. Do not give judges only the old Flask repository URL.

## Public sources reviewed

- [Official Future Health Digital Innovation Challenge](https://hack2skill.com/event/futurehealthchallenge/)
- [Loop Closer — DesignMaster Solutions repository](https://github.com/DesignMaster-Solutions/loop-closer) · [live demo](https://loop-closer.designmaster.workers.dev)
- [LoopShield — Agnuxo1 repository](https://github.com/Agnuxo1/loopshield) · [interactive demo](https://agnuxo1.github.io/loopshield/interactive.html) · [reviewer guide](https://agnuxo1.github.io/loopshield/review-guide.html)
- [CareLoop — ossolola repository](https://github.com/ossolola/careloop)
- [CareLoop — SOLIFAN / solidfdn repository](https://github.com/solidfdn/careloop) · [live demo](https://careloop-demo-864232222461.asia-northeast1.run.app/entry/)
- [CareTrack — HIMForward](https://caretrack.himforward.com/) · [judge page](https://caretrack.himforward.com/judges) · [guided demo](https://caretrack.himforward.com/demo) · [technical docs](https://caretrack.himforward.com/technical)
- [Lupora](https://www.lupora.life/)
- [JahanZari — Screening-to-Care Loop](https://www.jahanzari.com/)
- [OLL4 — LoopCloser prototype description](https://oll4.com/)

The official organiser's published results, private submissions and evaluation scores were not available to this review at the evidence cut-off.
