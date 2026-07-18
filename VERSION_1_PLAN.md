# Opportune Version 1 Execution Plan

**Basis:** `VERSION_1_AUDIT.md` at commit `b24d49e44b5a3bf4297c3d656eb3e848dd92218b`.

**Primary outcomes:**

1. An active approved profile receives useful visible listings, or a precise safe explanation identifies the first zero-result stage.
2. `opportune run` opens the local dashboard automatically; `opportune desktop` provides app-window mode where available and falls back cleanly.

The detailed onboarding and explicit approval gate remain mandatory. Native desktop wrappers, email/outreach/application-evidence features and hosted analytics are deferred.

## Program rules

- Prefer deterministic normalization, classification and gates over new AI.
- Approved profile versions are immutable. Editing creates a draft and requires re-approval before optional activation.
- No source task starts without one shared active `ApprovedProfileContext`.
- Source count is not source quality; add sources only after measured funnel gaps.
- Normal users do not need Node/npm.
- Local pilot instrumentation is off by default and never uploads automatically.
- Every item produces tests and user-visible evidence; code presence is not completion.

## Immediate fixes

### V1-W01 — Canonicalize location preferences and recover current listings

- **Findings:** V1-01; P1 `Verified`.
- **Current implementation/problem:** `compile_search_config` preserves location input; `location_verdict` falls to literal custom matching. Sanitized current state: 6,494 catalog rows → 24 role matches → 0 location matches. Canonical U.S. replay → 19 combined candidates.
- **Design:** Shared `normalize_location_preference()` returns display value, canonical kind (`country`, `state`, `metro`, `remote_region`, `custom`), code and validation state. Explicit alias table only. Ambiguous/custom values require confirmation.
- **Likely files:** new `profile/normalization.py`; `onboarding/compiler.py`, `questions.py`, `ranking/guardrails.py`, `pipeline/query_strategy.py`, `frontend/src/onboarding/OnboardingWizard.tsx`; ordered data migration and tests.
- **Data/API:** Store display and canonical values in profile field envelope. Existing approved values migrate through backed-up ordered migration; ambiguity creates `needs_review`, never silent broadening.
- **Security/privacy/network:** Local-only; no new requests.
- **Tests:** aliases, states/cities, Remote US, non-U.S., ambiguous custom; compiler/guard consistency; migration idempotency; sanitized end-to-end fixture.
- **Exit evidence:** deterministic compatible listing becomes dashboard-visible; current stored catalog produces expected Pool/Review candidates after approved migration; no safety rule weakened.
- **Difficulty/dependencies:** Medium; first implementation item.

### V1-W02 — Add end-to-end discovery-funnel diagnostics

- **Findings:** V1-02/V1-14; P1.
- **Design:** versioned `discovery_funnel` counts and reason codes for tasks, requests, raw, normalized, geo, role, location, pool, ranking, freshness/link/lifecycle, buckets, persistence and dashboard. Preserve per-source breakdown.
- **Files:** `pipeline/scrape.py`, `dashboard/db.py`, `dashapi/server.py`, `jobhunt.py`, `frontend/src/App.tsx`, `frontend/src/api.ts` and tests.
- **API/UI:** scrape/smart/status responses include safe funnel; `opportune diagnose discovery --json`; empty state shows first zero stage, effective profile rules and edit-draft route.
- **Privacy:** no resume text, keys, raw prompts/full descriptions or private paths.
- **Exit evidence:** impossible-profile fixture reports exact first zero; partial source failures remain distinguishable; user gets a correction rather than generic emptiness.
- **Difficulty/dependencies:** Medium; builds on W01 and source table design.

### V1-W03 — Add one-command automatic launch

- **Finding:** V1-03; P1 `Verified`.
- **Current:** both console entry points exist; `dashboard/dash/start` print URL and block in Uvicorn; `opportune run` is invalid.
- **Design:** `opportune run` starts/attaches, polls health and actual assets, then opens default browser. `opportune desktop` prefers Chrome/Edge/Chromium `--app=<loopback URL>` and maximized mode; fallback to normal browser. Preserve aliases. Add `--no-open`, `--browser`, `--host`, `--port`.
- **Files:** `jobhunt.py`; new small `desktop_launcher.py`; `dashapi/server.py` remains server owner; `pyproject.toml` only if entry metadata changes; tests/docs/release workflow.
- **Safety:** loopback default, explicit opt-in for non-loopback opening, identify existing Opportune health response, actionable foreign-port conflict, bounded timeout, Ctrl+C cleanup.
- **Tests:** mocked browser/process discovery; readiness and asset integration; installed wheel outside checkout; real manual Windows/macOS/Linux launch.
- **Exit evidence:** one command opens the correct packaged dashboard on every declared OS; headless mode works.
- **Difficulty/dependencies:** Medium; package smoke already establishes current wheel/assets work on WSL/Linux.

### V1-W04 — Correct immediate public claims and package manifest

- **Findings:** V1-08/V1-09/V1-17/V1-19.
- **Actions:** replace absolute privacy text; state current alpha scope; remove normal-user Node build; reconcile tag/no GitHub Release; review/remove bundled candidate/resume artifacts unless clearly synthetic and required.
- **Files:** README, SECURITY, ARCHITECTURE, ROADMAP, CHANGELOG, PUBLIC_RELEASE, `pyproject.toml`, package-content tests.
- **Exit evidence:** docs, metadata, package manifest and UI disclosures agree; no personal resume/profile artifact ships.
- **Difficulty:** Low-medium.

## Release blockers

### V1-W05 — Centralize active approved profile context

- **Finding:** V1-04.
- **Design:** new immutable `ApprovedProfileContext(profile_id, version_id, schema_version, revision, compiled_config)`. Resolve once at lowest common discovery/ranking boundary. Benchmarks inject explicit synthetic context.
- **Call sites:** FastAPI routes, CLI scrape/smart, scheduler once/recurring, smart scrape, scrape, pool rebuild, agent commands, ranking entry points.
- **Tests:** no profile, draft, inactive, deleted, superseded; patch lowest source boundary and assert zero calls; switch active versions and assert ranking context changes; scheduler fails boundedly.
- **Exit:** zero bypasses and no default/empty-profile fallback.
- **Difficulty/dependencies:** Medium-high; coordinate with profile version work.

### V1-W06 — Introduce versioned drafts and immutable approval

- **Findings:** V1-05/V1-06/V1-07.
- **Target state:** resume analysis → versioned draft → progressive saved corrections → effective preview → explicit approval → immutable version → activation.
- **Tables:** stable `profiles`; `profile_versions`; `profile_field_values`; `profile_rejections`; draft-linked `onboarding_sessions`; single active-approved-version pointer.
- **Field statuses:** `extracted`, `inferred`, `user_added`, `confirmed`, `rejected`, `needs_review`.
- **Routes:** create/get/patch/analyze/preview/approve draft; create draft from approved profile; activate approved version. PATCH uses expected revision/ETag and returns 409 with latest state on conflict.
- **UI:** progressive sections, progress, auto-save/resume, editable extraction/evidence, why-it-matters examples, live effective profile, explicit freshness, final assumptions/exclusions/provider review.
- **Migration:** ordered backup-preserving import from current profiles/session JSON. Approved current behavior remains active until new draft approval.
- **Exit:** no mandatory field lost; refresh/restart/conflict/rejection/edit-copy/profile-switch E2E pass.
- **Difficulty/dependencies:** High; W05 and migration runner.

### V1-W07 — Establish ordered database and platform-data migration

- **Findings:** V1-10/V1-13.
- **Decision:** prefer a small ordered SQLite runner with migration IDs and `PRAGMA user_version`/journal unless an ORM/Alembic need is demonstrated.
- **Data roots:** evaluate `platformdirs`; separate config/data/cache/log/export/backup; never default beside package modules/assets.
- **Migration:** detect legacy `tracker/`, report/dry-run, backup, copy/verify integrity and counts, atomic switch, preserve old until success, idempotent rerun.
- **Lifecycle commands:** inspect/export/backup/restore/reset jobs/full wipe/uninstall; backup removal separate explicit choice.
- **Tests:** previous-release DB fixtures, interrupted/corrupt cases, foreign keys/counts, symlinks, restore ZIP traversal, active profile preservation.
- **Exit:** clean install and upgrade on every supported OS without loss or unwritable package state.
- **Difficulty:** High.

### V1-W08 — Complete privacy/security release matrix

- **Findings:** V1-08/V1-13/V1-19/V1-20.
- **Tests:** resume traversal/size/MIME/malformed parser/resource bounds; listing script/unsafe schemes/target opener; host/origin mutations; key/resume/path/exception redaction; backup/restore/wipe/symlink; corrupt/interrupted DB/migration.
- **Disclosure labels:** local; free; free with limits; requires API key; paid; sends resume externally; reads public job data externally.
- **Exit:** no path escape, script execution, unsafe mutation, secret disclosure, ambiguous destructive action or unrecoverable partial migration.
- **Difficulty:** Medium-high.

### V1-W09 — Build reproducible public full-pipeline benchmark

- **Finding:** V1-11.
- **Deliverable:** implement `BENCHMARK_SPEC.md`: schemas, scenario-derived dataset, development/validation/frozen final split, leakage checks, human labels/adjudication, deterministic runner, raw predictions, metrics/segments/confidence intervals and gates.
- **Exit:** agreed final-test and safety-segment gates pass without tuning on final-test failures.
- **Difficulty:** High; requires V1 capability decision.

### V1-W10 — Implement source-quality measurement

- **Finding:** V1-12.
- **Deliverable:** implement `SOURCE_QUALITY_SPEC.md` tables, adapter instrumentation, responsible dead-link validation, local report/export and free/paid comparison.
- **Exit:** every enabled source has measured yield/freshness/failure/latency/cost/retention evidence; expansion decisions use gaps, not registry size.
- **Difficulty:** High; depends on migration runner and W02 vocabulary.

## High-impact improvements

### V1-W11 — Make dashboard decisions trustworthy

- Add Ready/Review/Excluded mapping; decisive evidence, uncertainties and correctable profile inputs; first-zero and partial-source state; last success and lifecycle/link freshness; score subordinate to decision evidence.
- Test persistence/reload for save, hide, applied and filters.
- Exit: user can explain what to do next and why.

### V1-W12 — Add accessibility and recoverable-error gates

- Add justified frontend component/E2E/a11y tooling.
- Keyboard/focus/dialog/error summary/live progress/labels/color-independent state/reduced-motion/contrast/200% zoom/320px reflow.
- Exit: no serious/critical automated violations; manual keyboard checklist passes release artifact.

### V1-W13 — Create release artifact and OS workflows

- `.github/workflows/release.yml`: build frontend once, wheel/sdist, manifest/version/checksum, isolated install outside checkout, health/onboarding/asset smoke, upload GitHub Release only after approval.
- Platform matrix: Windows 11 x64, Ubuntu 22.04/24.04 x64, supported macOS current/previous; WSL/Docker separate.
- Docker Compose secondary with loopback and mounted data volume.
- Exit: only artifact-tested platforms are called supported.

### V1-W14 — Run invited local-first pilot

- Implement opt-in local events and inspectable report/export from `PILOT_TEST_PLAN.md`.
- Recruit 8–12 representative early-career job seekers across OS, role and authorization groups.
- Measure install, launch, onboarding, first good listing, top-5/10, trust/privacy, repeat runs and applications.
- Exit: pilot thresholds pass or findings return to immediate fixes.

## Later Version 1 improvements

1. Improve adapters/source coverage only from measured source gaps.
2. Tune deterministic ranking using development/validation sets, never frozen final test.
3. Improve explanations where benchmark consistency/pilot trust is weak.
4. Add convenience platform startup scripts if wheel launcher evidence shows need.
5. Publish benchmark and source reports with known limitations.
6. Convert accepted `CONTRIBUTOR_BACKLOG.md` proposals into GitHub Issues after duplicate review.

## Deferred Version 2

- Email monitoring or application-evidence ingestion.
- Outreach/contact discovery or message generation.
- Automatic applications.
- Hosted analytics, remote synchronization or multi-user service.
- Tauri/Electron/native desktop shell.
- Paid-source expansion without measured free-source gaps.

V2 does not start until installation, onboarding completion, useful free-source coverage, ranking/safety benchmark, real applications and repeat usage pass the V1 scorecard.

## Dependency order

```text
W01 location fix ─┬─> W02 funnel ───────────────┐
                  └─> current listing proof     │
W03 launcher ─────────> W13 release matrix      │
W07 migration ──┬─> W06 profile versions ─> W05 approval context
                ├─> W10 source tables           │
                └─> W08 data security           │
W09 benchmark ──────────────────────────────────┤
W11 dashboard + W12 accessibility ──────────────┤
W04 truthful docs/package ──────────────────────┤
                                                └─> W14 pilot -> ship/no-ship
```

## Evidence produced per work item

Each implementation PR must include:

- finding ID and exact current evidence;
- architecture/data/API/migration/privacy/network impact;
- smallest relevant unit/integration/browser/platform tests;
- exact commands and outputs;
- user-visible screenshot/report where applicable;
- scorecard row updates;
- no secret/private runtime artifacts;
- no push until maintainer review.

## Maintainer decisions required before code implementation

1. V1 recommendation scope: early-career applied AI/AI engineering only, or broader deterministic role support?
2. Exact native OS support matrix after artifact runs.
3. Benchmark scenario matrix, derived label count and hard thresholds.
4. Invited pilot scope and recipient of voluntary anonymized exports.
5. Full-wipe backup preservation default.
6. Which benchmark thresholds become non-waivable release gates.

Until these are approved, the eight documents are the completed execution output; product code and GitHub Issues remain unchanged.
