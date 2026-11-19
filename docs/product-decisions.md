# Product decisions: original OneCare Loop and public challenge research

This document records which product ideas informed OneCare Loop v2 and which original implementation details were deliberately not carried forward. The competitor review informed the requirements checklist and demonstration strategy; no competitor source code was copied into this project.

## Retained from the original OneCare Loop prototype

- **A visible care journey:** screening, referral, acceptance, appointment, attendance, clinician outcome and follow-up remain the product's central narrative.
- **Patient-facing receipt:** patients can review a chronological, verifiable history and acknowledge that they have read it.
- **Failure is a first-class outcome:** a declined referral, missed appointment, unreachable patient or reschedule request remains visible instead of being hidden by a new referral.
- **A single coherent product surface:** the pharmacy, hospital, clinician, administrator and patient experiences are served by one deployable application.
- **Clear visual identity:** the FastAPI release keeps a branded, responsive interface rather than presenting only Swagger endpoints.

## Original implementation details deliberately not carried forward

The original Flask repository contained useful workflow concepts and visual presentation, but the second audit also found unsafe public role selection, unauthenticated patient-data endpoints, caller-supplied actor identities, development impersonation, weak password hashing, predictable development defaults and unsafe dynamic HTML insertion. The FastAPI project uses a separate authenticated domain/service architecture instead of copying those route handlers or demo shortcuts.

## Lessons from publicly visible challenge projects

| Public pattern observed | OneCare Loop v2 design decision |
|---|---|
| Detailed requirement-to-feature mapping and test evidence (Loop Closer, LoopShield) | Keep an explicit workflow/API guide, release validation, judge guide and regression tests for the critical challenge outcomes. |
| Confirmatory testing appears as a distinct step (Loop Closer, CareTrack) | Require the assigned clinician to record a confirmatory method or a documented not-indicated decision before returning a disposition. |
| Named case ownership, deadline clocks and overdue/unassigned worklists (LoopShield, CareTrack, CareLoop) | Assign ownership on hospital acceptance and clinician attendance; support facility-scoped reassignment and operational-attention views. |
| Missed, rejected or corrected referral/result pathways (Loop Closer, LoopShield, SOLIFAN CareLoop) | Preserve the declined referral and allow a later redirect to a new referral with a fresh SLA; retain corrections as explicit evidence events. |
| Patient communication, understanding and consultation (Loop Closer, CareTrack) | Keep patient acknowledgement and encrypted care-team messaging; make simulated notification status explicit and do not claim delivery. |
| Guided judge stories and one-click demonstrations (LoopShield, CareTrack) | Add `/demo` linked from the homepage. It creates a synthetic case through real FastAPI services and animates its persisted event history; replay does not create duplicate records. |
| Standards-based inbound/outbound interoperability (Loop Closer, CareTrack) | Retain FHIR R4 export and document the remaining gap: no HL7 v2 ORU ingestion or external validator/round-trip result yet. |
| Privacy-preserving AI assistance (LoopShield, CareLoop) | Do not add an unvalidated LLM to the hypertension prototype. Use deterministic care workflow, encrypted data and human clinical decisions. |

## Deliberate boundaries

- The application coordinates care; it does not diagnose, prescribe or choose a clinical confirmatory method.
- The clinician makes the confirmatory assessment decision. The system only enforces that the decision is documented before disposition.
- The SLA CLI creates an operational exception. It is not a live coordinator, emergency service or patient-contact integration.
- Eligibility is explicitly unknown while no NHIA/DHIN integration exists.
- Synthetic test results demonstrate software behaviour only; they do not establish clinical validity or improved population outcomes.

## Why this is a focused prototype

The initial pilot pathway remains community hypertension screening through a pharmacy/PMV, receiving hospital, assigned clinician and follow-up. Broader disease pathways, payer automation, national exchange integrations and emergency dispatch depend on clinical governance, provider agreements, interoperability testing and operational partners. Those are documented as future work rather than simulated as completed integrations.

## Current public competitor review

The public project scan and weighted evidence scorecard are maintained in `docs/public-competitor-benchmark.md`. It includes recursive GitHub tree comparisons for Loop Closer, LoopShield, both public CareLoop repositories and the local FastAPI candidate, plus lower-confidence public-demo/website assessments for CareTrack, Lupora and OLL4. The official challenge platform does not expose an exhaustive public entrants list, so the review does not claim to score every applicant.

The benchmark also records the important publication mismatch: the FastAPI candidate is currently a local release package while public `main` still contains the older Flask implementation. The exact code/branch/demo sent to judges must be aligned before submission.
