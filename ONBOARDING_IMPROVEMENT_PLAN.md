# Opportune Version 1 Onboarding Improvement Plan

## 1. Non-negotiable product decision

Onboarding remains detailed and mandatory. Discovery and production ranking may not start from an unapproved profile.

Required information remains:

1. Target roles and work focus.
2. Experience and realistic job levels.
3. Skills and resume evidence.
4. Preferred locations and work modes.
5. Work authorization and sponsorship constraints.
6. Listing freshness preferences.
7. Exclusions and other search constraints.

The goal is lower effort and higher trust through extraction, confirmation, progress, auto-save, correction and preview—not fewer questions.

Required privacy language before provider selection:

> Profiles, jobs, notes, and application data remain on the user’s machine. Resume analysis can remain fully local. When a user intentionally selects an external model provider, necessary resume content may be sent to that provider after best-effort redaction.

## 2. Current evidence

- `onboarding/questions.py:build_questions` groups five detailed prompts covering most required areas.
- `onboarding/compiler.py:compile_search_profile/compile_search_config` builds the effective profile; freshness defaults to seven days.
- `onboarding/store.py` stores sessions/answers in SQLite.
- `onboarding/service.py` orchestrates analysis/review/approval.
- `frontend/src/onboarding/OnboardingWizard.tsx` provides staged provider/resume/analysis/questions/review flow.
- API scrape/smart/pool routes use `dashapi/server.py:_require_approved_profile`.
- Interim answers are primarily held in React until review submission; immutable versions, per-field provenance/rejection and revision-safe auto-save are not fully represented.
- A compact U.S. location value can survive compilation and be treated as a literal custom location by `ranking/guardrails.py:location_verdict`, causing zero results.

These are static/targeted runtime observations. Completion rate, time and comprehension require the pilot.

## 3. Target lifecycle

```text
Resume analysis
  → versioned onboarding draft
  → progressively saved corrections and answers
  → complete effective-profile preview
  → explicit approval
  → immutable approved profile version
  → activation
```

Editing an approved profile creates a new draft based on it. The active approved version remains unchanged until the new draft is explicitly approved and activated.

## 4. Data model

### `profiles`

Stable identity only: `profile_id`, display name, created/updated timestamps.

### `profile_versions`

- `version_id` PK;
- `profile_id` FK;
- `version_number` monotonically increasing per profile;
- `state`: draft/approved/superseded;
- `base_version_id` nullable;
- `schema_version`, `revision`;
- resume retention/reference policy;
- created/updated/approved timestamps.

Approved rows and associated field values are immutable.

### `profile_field_values`

- `field_value_id`, `version_id`, `field_path`;
- `value_json`;
- `source`: resume/model/user/default/migration;
- `evidence_json`;
- `confidence` nullable;
- `status`: extracted/inferred/user_added/confirmed/rejected/needs_review;
- `extraction_run_id` nullable;
- `user_modified_at`, timestamps.

After user confirmation, the user’s decision outranks model confidence; retain original extraction confidence only as provenance.

### `profile_rejections`

Normalized rejection fingerprint scoped to profile/field/value plus reason/timestamps. Later analysis must consult it before proposing the same value.

### `onboarding_sessions`

Link to `draft_version_id`, current section, completion map, last saved revision and timestamps. It is not a second source of approved truth.

### Active pointer

A single app-state pointer references exactly one approved profile version. Activation rejects draft/missing/deleted/superseded versions.

## 5. API contract

- `POST /api/onboarding/drafts` — create from resume or approved base version.
- `GET /api/onboarding/drafts/{draft_id}` — resumable fields, provenance, completion, validation and revision.
- `PATCH /api/onboarding/drafts/{draft_id}` — idempotent field operations with expected revision/ETag.
- `POST /api/onboarding/drafts/{draft_id}/analyze` — extraction honoring durable rejections.
- `POST /api/onboarding/drafts/{draft_id}/preview` — complete effective profile without activation.
- `POST /api/onboarding/drafts/{draft_id}/approve` — transactional validation/freeze.
- `POST /api/profile-versions/{version_id}/activate` — approved versions only.
- `POST /api/profiles/{profile_id}/drafts` — edit-copy from approved version.

PATCH increments revision. Stale revision returns `409 Conflict` with latest server revision/state and recoverable conflicting field paths. Do not use silent last-write-wins.

## 6. Improvement matrix

### OI-01 — Progressive sections and honest progress

- **Current friction:** five large prompts combine several decisions; users cannot see field-level completion.
- **Interface change:** sections for goals, experience, evidence/skills, location/work mode, authorization, freshness, exclusions, final review. Progress is based on validated required fields, not page count alone.
- **Information preserved:** all seven groups.
- **Ranking effect:** none directly; fewer missed/contradictory fields.
- **Files:** `questions.py`, `OnboardingWizard.tsx`, `types.ts`, onboarding CSS, API validation.
- **Tests:** section completion rules, keyboard progress semantics, refresh between sections, missing-field summary.
- **Acceptance:** no required field removed; progress accurately reflects completion and is announced semantically.

### OI-02 — Resume-based prefill with confirmation

- **Current friction:** users repeat information already present in resume while extracted evidence can be accepted without enough scrutiny.
- **Interface change:** prefill roles, level evidence, skills/projects and likely locations/work modes; show source/evidence/confidence/status; require confirm/edit/reject.
- **Information preserved:** target roles, level, skills/evidence, location/work mode.
- **Ranking effect:** stronger evidence while preventing unsupported inference.
- **Files:** providers/compiler/service, field schema, wizard editors.
- **Tests:** extraction envelope, low-confidence Review, user confirmation precedence, no prediction shown as confirmed.
- **Acceptance:** every extracted field is individually correctable/rejectable and approval cannot hide unresolved required `needs_review` fields.

### OI-03 — Durable rejection and re-analysis protection

- **Current friction:** a value rejected by the user can be regenerated by another analysis.
- **Interface change:** rejected values remain visible in an optional history with restore; analysis respects fingerprints.
- **Information preserved:** user decision and extraction provenance.
- **Ranking effect:** prevents recurring false skills/roles/locations.
- **Files:** `profile_rejections`, provider/service merge logic, review UI.
- **Tests:** reject→reanalyze does not reintroduce; edited variant policy; restore; migration.
- **Acceptance:** no exact normalized rejected value returns without explicit user action.

### OI-04 — Per-section auto-save and resume later

- **Current friction:** interim React state can be lost before final review; no revision conflict model.
- **Interface change:** debounced/blur field PATCH, visible saved/saving/error state, explicit Resume Later, server-backed current section.
- **Information preserved:** all draft answers/corrections/provenance.
- **Ranking effect:** no direct change; prevents incomplete fallback/default profiles.
- **Files:** store/service/server routes; API client; wizard state.
- **Tests:** refresh/restart/offline failure/retry, duplicate idempotency, stale revision 409 and conflict resolution.
- **Acceptance:** latest acknowledged revision survives restart; errors are actionable and unsaved state is never falsely labeled saved.

### OI-05 — Plain-language “why this matters” examples

- **Current friction:** fields can look bureaucratic, especially authorization, work mode, freshness and exclusions.
- **Interface change:** concise expandable help per field showing “Change here → discovery/ranking reacts like this.”
- **Information preserved:** unchanged.
- **Ranking effect:** users set rules intentionally rather than guessing.
- **Files:** question metadata, wizard help components/copy tests.
- **Tests:** required copy inventory, accessible disclosure controls, examples consistent with deterministic code.
- **Acceptance:** every mandatory group has a tested example; no overpromise or hidden safety relaxation.

### OI-06 — Canonical location confirmation

- **Current friction:** equivalent U.S. inputs can become literal custom locations and yield zero jobs.
- **Interface change:** parse to display/canonical values; show “United States — nationwide,” Remote US, state/metro interpretation; ambiguous custom values require correction/confirmation.
- **Information preserved:** original user text as provenance plus canonical rule.
- **Ranking effect:** fixes role matches eliminated by malformed location while preserving explicit geography.
- **Files:** new normalization module; compiler/questions; guardrails/query strategy; migration; wizard preview.
- **Tests:** compact/canonical aliases, U.S. cities/states, remote, non-U.S., ambiguous custom, end-to-end zero-result regression.
- **Acceptance:** equivalent values behave identically; ambiguity never silently broadens search; sanitized current reproduction yields candidate pool.

### OI-07 — Explicit realistic level review

- **Current friction:** resume-derived level and user target level can be conflated; senior negatives need clear handling.
- **Interface change:** separate “evidence suggests” from “levels to search”; show examples of exclusion/Review behavior.
- **Information preserved:** experience evidence and selected target levels.
- **Ranking effect:** fewer unsafe senior recommendations and fewer false exclusions for adjacent levels.
- **Files:** compiler/field schema, targeting/preview, wizard.
- **Tests:** new-grad/entry/junior/mid/senior, conflicting resume evidence, multiple target levels.
- **Acceptance:** approval shows both inferred current level and chosen target levels; conflicts require confirmation.

### OI-08 — Authorization and sponsorship safety review

- **Current friction:** users may not understand candidate status versus employer policy/ambiguity.
- **Interface change:** separate candidate authorization, current/future sponsorship need, clearance/citizenship constraints and ambiguous-language policy; show hard-gate examples.
- **Information preserved:** all authorization constraints.
- **Ranking effect:** prevents unsafe Ready decisions; ambiguity moves to Review.
- **Files:** questions/compiler/eligibility/guardrails, preview UI, benchmark fixtures.
- **Tests:** sponsorship available/unavailable/ambiguous, citizenship/clearance, no unauthorized Ready.
- **Acceptance:** final review states exact rules; no source/discovery occurs before approval.

### OI-09 — User-confirmed freshness preference

- **Current friction:** seven-day default is hidden.
- **Interface change:** required choice with presets/custom days, unknown-date behavior and examples.
- **Information preserved:** explicit freshness constraint.
- **Ranking effect:** predictable old/unknown handling.
- **Files:** questions/compiler/profile schema, preview UI, freshness/ranking tests.
- **Tests:** presets/custom validation, unknown dates, old dates, timezone boundary.
- **Acceptance:** approved profile contains confirmed value; unknown never labeled fresh without evidence.

### OI-10 — Provider privacy/cost/network decision before analysis

- **Current friction:** existing warning does not consistently expose local/free/key/paid/external data labels.
- **Interface change:** provider cards with all applicable labels, exact resume payload disclosure, redaction limitations and explicit acknowledgment before remote send.
- **Information preserved:** provider choice and consent record.
- **Ranking effect:** none; trust/privacy protection.
- **Files:** providers metadata/service, wizard, SECURITY/README, API consent schema.
- **Tests:** local sends zero remote calls; remote requires consent/key as applicable; custom endpoint classified by actual URL; payload/log redaction.
- **Acceptance:** user understands what leaves machine before action; exact privacy wording is present.

### OI-11 — Live effective search-profile preview

- **Current friction:** users answer fields separately but cannot see the compiled query/ranking policy.
- **Interface change:** continuously updated summary of role families/titles, levels, locations/work modes, authorization, freshness, exclusions, provider/source behavior and unresolved assumptions.
- **Information preserved:** all fields plus compilation result.
- **Ranking effect:** exposes defaults/normalization before approval.
- **Files:** preview route/compiler, API client, wizard preview component.
- **Tests:** preview equals config consumed by discovery/ranking; no activation; changes update revision; accessibility.
- **Acceptance:** what the user approves is byte/semantically equivalent to activated compiled config.

### OI-12 — Final review and atomic approval

- **Current friction:** review does not fully separate assumptions, unresolved inference, exclusions and effective rules; current profile state is mutable.
- **Interface change:** grouped final page with edit links and explicit approval statement; approve transaction freezes version, then optional activation.
- **Information preserved:** entire version, provenance, rejections and consent.
- **Ranking effect:** only reviewed rules become production context.
- **Files:** version tables/store/service/routes, wizard review, `ApprovedProfileContext` service.
- **Tests:** incomplete approval blocked; transaction rollback; immutability; edit creates draft; activate only approved; switch context.
- **Acceptance:** no draft/unapproved/inactive version can trigger any source request or production rank.

### OI-13 — Actionable validation and error recovery

- **Current friction:** network/parser/conflict/field errors can interrupt a long flow without a clear recovery path.
- **Interface change:** field errors linked to controls; focusable page summary; retry/resume; provider and upload diagnostics; preserved input.
- **Information preserved:** all valid draft state.
- **Ranking effect:** prevents accidental approval of defaults after failure.
- **Files:** FastAPI errors, API client, wizard, CSS/test harness.
- **Tests:** malformed/oversized resume, provider timeout, 409, server restart, keyboard/screen-reader announcement.
- **Acceptance:** errors identify cause/action without secrets/paths; recovery does not discard acknowledged state.

### OI-14 — Zero-result correction loop

- **Current friction:** user sees no jobs but cannot tell whether source, normalization, role, location, eligibility or ranking caused it.
- **Interface change:** after approved run, show discovery funnel and “Edit a new draft” action prefilled from active version. Never mutate active approved rules silently.
- **Information preserved:** active approved version and new draft history.
- **Ranking effect:** corrects overly narrow/invalid intent transparently.
- **Files:** scrape funnel, diagnostics API, dashboard empty state, draft-from-approved route.
- **Tests:** each first-zero stage, edit-copy/approve/activate rerun, no source call before new approval.
- **Acceptance:** current compact-location regression points to location and recovery; valid narrow searches are explained, not auto-broadened.

## 7. Migration plan

1. Add ordered schema runner and back up DB.
2. Create profile/version/field/rejection/activation tables.
3. For each current profile, create stable profile and version 1 from `extracted_json`; mark active version approved only when current evidence says onboarding approved/active, otherwise draft/needs review.
4. Convert session answers to draft fields and preserve timestamps where available.
5. Normalize recognized locations; ambiguous values become `needs_review` without activation change until user confirms.
6. Validate row counts, foreign keys, one active approved pointer and compiled-config equivalence.
7. Keep legacy columns read-only during compatibility window; remove only in a later migration after export/rollback evidence.
8. On any failure, retain backup/source DB and do not partially activate new schema.

## 8. Test matrix

### Unit

Field state transitions, normalization, compiler equivalence, rejection merge, completion rules, revision operations, consent metadata.

### API integration

Draft create/get/patch/analyze/preview/approve/activate, stale revision, idempotency, transaction rollback, active-version enforcement, zero network calls.

### Browser E2E

Local provider and consented remote-provider paths; resume extraction; correction/rejection; every section; auto-save/refresh/restart; conflict recovery; preview; final review; approve/activate; edit-copy; profile switching; zero-result correction.

### Accessibility/security

Keyboard/focus/error summary/progress/live region/zoom/reduced motion/contrast; upload traversal/size/MIME/malformed parser; secret/path redaction.

### Migration/platform

Previous-release fixtures and current compact-location fixture on every supported OS; backup/integrity/idempotency/interruption recovery.

## 9. Completion criteria

Onboarding is complete only when:

- all seven information groups and provenance are preserved;
- user corrections/rejections are durable;
- refresh/restart/conflict recovery passes;
- effective preview equals production context;
- provider disclosure and consent are explicit;
- approval is atomic and immutable;
- only active approved versions can discover/rank;
- pilot completion/time/privacy thresholds pass;
- no safety gate was weakened to increase listing count.
