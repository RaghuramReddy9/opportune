# Opportune Version 1 Audit

**Audited commit:** `b24d49e44b5a3bf4297c3d656eb3e848dd92218b` (`main`)

**Audit date:** 2026-07-18

**Verdict:** **Not release-ready for a broad Version 1 claim.** The repository has a substantial tested foundation, but the core user outcome can still fail: a valid approved profile may receive zero visible jobs because equivalent location inputs are not canonicalized. Installation also lacks the requested automatic browser/app launch, and ranking/source quality is not yet supported by a contamination-resistant public benchmark or live source-quality report.

## Evidence rules

Finding classifications are exactly:

- `Verified`: directly established by repository state or a runtime check at the audited commit.
- `Partially verified`: a production path was traced, but one or more runtime boundaries remain untested.
- `Requires runtime testing`: the claim needs clean-OS, browser, live-source, migration, security, or pilot execution.
- `Proposal`: target behavior or architecture not implemented now.
- `Not reproduced`: an alleged issue was tested and was not observed.

Severity is separate: P0 is reserved for demonstrated security/privacy/destructive-data blockers; P1 is a major product/adoption failure; P2 is important quality/usability; P3 is polish.

## Executive findings

1. **The current empty dashboard is not caused by a lack of source data.** Read-only state showed 6,494 active catalog listings and zero dashboard jobs. A compact U.S. location token was treated as a literal custom location, eliminating all 24 role-title matches. An in-memory replay with canonical `United States` produced 19 role+location candidates. This is the first V1 fix.
2. **The installed wheel is healthier than the README implies.** A wheel built and installed into an isolated environment; `opp` and `opportune` entry points worked; `/`, `/api/health`, `/api/onboarding`, and referenced JS/CSS/favicon assets returned HTTP 200. Normal users should not need Node. The installed data-directory location remains unverified because that follow-up inspection was denied.
3. **One-command launch is only partial.** `opp start`/`dashboard` starts Uvicorn and prints a URL. `opportune run` fails as an unknown command, and no current handler waits for readiness or opens a browser.
4. **Current automated quality is real but narrow.** `257 passed in 38.20s`; Ruff and frontend lint/build passed. The legacy ranking gate passed on 16 fixtures with exact-bucket accuracy 0.9375 and one error. This is regression evidence, not broad recommendation-quality evidence.
5. **No P0 is asserted.** Several P1 privacy/security/data-lifecycle items require testing or correction, but this audit did not prove unauthorized disclosure or destructive loss.

## Verified strengths

| Strength | Classification and evidence | Limits |
|---|---|---|
| Backend regression suite | `Verified`; `uv run python -m pytest tests/ -q` → `257 passed in 38.20s`. | Tests do not establish live-source quality, accessibility, or native OS support. |
| Python quality check | `Verified`; `uv run ruff check .` → `All checks passed!`. | Static style only. |
| Frontend build | `Verified`; `frontend`: `npm run lint` → 0 warnings/errors; `npm run build` → 1,778 modules, production assets generated successfully. | No component/E2E/a11y suite is configured. |
| Legacy ranking gate | `Verified`; `uv run opp quality --json`: 16 fixtures, 0.9375 exact bucket accuracy, 1.0 Apply precision, 1.0 surface recall, 0 unsafe false applies, one Apply→Watch error. | One profile, tuned fixtures, no split, no confidence intervals or segment report. |
| Wheel and served assets | `Verified`; `uv build`; isolated wheel install; both console scripts passed `--help`; installed server returned 200 for `/`, health, onboarding, favicon, JS and CSS. | Data location, upgrades and Windows/macOS remain unverified. |
| Explicit web approval gate | `Partially verified`; `dashapi/server.py:_require_approved_profile` is called by scrape/smart/pool routes; corresponding tests exist. | Other entry points do not visibly share the same lowest-boundary service. |
| Deterministic ranking/safety modules | `Partially verified`; `ranking/score.py`, `targeting.py`, `eligibility.py`, `guardrails.py`, `core/dedupe.py`, `core/skill_matcher.py`. | Full-pipeline accuracy and explanations are unmeasured. |
| Local operational controls | `Partially verified`; `public_ops.py:backup_local_state`, `wipe_local_data`; SQLite snapshot behavior and tests exist. | Restore/full wipe/migration interruption semantics are incomplete. |

## Detailed findings

### V1-01 — Equivalent U.S. location input can eliminate all results

- **Severity / classification:** P1 / `Verified` (static trace plus read-only runtime reproduction).
- **Affected users:** Users who type or receive compact/variant location values during onboarding.
- **Evidence:** `onboarding/compiler.py:compile_search_config` preserves the answer string; `ranking/guardrails.py:location_verdict` recognizes canonical U.S. forms but otherwise uses literal custom-location matching; `pipeline/discovery_pool.py:match_role_preference` and `prepare_pool_job`. Read-only `tracker/dashboard.db`: 6,494 active catalog rows, 24 role matches, zero location and combined matches, zero `jobs`. Canonical U.S. in-memory replay produced 19 role+location candidates (6 mid, 11 senior, 2 unknown).
- **Uncertainty:** Replay stopped before live link validation/final ranking; it predicts candidates, not final Ready quality.
- **Proposed solution:** One shared strict location normalizer with display value plus canonical type/code, onboarding confirmation, migration of existing profile versions, and regression aliases. Do not use broad fuzzy guessing.
- **Likely implementation:** new `profile/normalization.py`; modify `onboarding/compiler.py`, `onboarding/questions.py`, `ranking/guardrails.py`, `pipeline/query_strategy.py`, profile migration, onboarding preview UI; tests in `tests/test_location_normalization.py`, discovery/onboarding/pipeline suites.
- **Privacy/network:** Local deterministic transformation; no new network or resume exposure.
- **Tests:** alias/unit and compiler/guard consistency; migration backup/idempotency; sanitized full-pipeline fixture and current-catalog replay.
- **Dependencies:** ordered migration support for existing profile rows; no source expansion dependency.
- **Difficulty / impact:** Medium / critical core-loop recovery.
- **Acceptance:** Equivalent U.S. variants compile identically; ambiguous values require review; deterministic fixture produces a safe visible job; existing profile migration is backed up, idempotent and preserves approval rules.

### V1-02 — Zero-result runs are not diagnosable by users

- **Severity / classification:** P1 / `Partially verified` (static pipeline/UI trace).
- **Affected users:** Anyone receiving an empty dashboard or partial source failure.
- **Evidence:** `pipeline/scrape.py:scrape_all` exposes aggregate counts but no stable complete source→filter→rank→persist→UI funnel; `dashapi/server.py` scrape/smart responses; `frontend/src/App.tsx` empty/status states; current reproduction required custom read-only analysis.
- **Proposed solution:** Versioned `discovery_funnel` with normalized reason codes and per-source breakdown; dashboard empty state identifying first zero stage and effective search rules; `opportune diagnose discovery --json` with private fields redacted.
- **Likely implementation:** `pipeline/scrape.py`, `dashboard/db.py` source run tables, `dashapi/server.py`, `jobhunt.py`, `frontend/src/App.tsx`, API types/tests/E2E.
- **Privacy/network:** Store counts/reason codes, not resume text, keys, raw descriptions or full URLs.
- **Tests:** one offline fixture for every first-zero stage, partial source failure, persistence/API serialization, UI empty state and diagnostics redaction.
- **Dependencies:** shared source-run vocabulary and location normalization for the verified reproduction.
- **Difficulty / impact:** Medium / high trust and supportability.
- **Acceptance:** Every zero-result fixture reports the first zero stage and a safe correction; no safety constraint is silently relaxed to manufacture jobs.

### V1-03 — No requested one-command browser/app launch

- **Severity / classification:** P1 / `Verified` (static plus CLI runtime).
- **Affected users:** Nontechnical users and anyone expecting terminal-to-app launch.
- **Evidence:** `pyproject.toml:[project.scripts]` already exposes `opp` and `opportune`; `jobhunt.py:cmd_dashboard` prints URL and directly calls `dashapi.server.run`; parser aliases are `dashboard`, `dash`, `start`. `uv run opportune run --help` exited 2: invalid command. No readiness polling/browser opener exists.
- **Proposed solution:** `opportune run` starts/attaches, waits for health/assets and opens default browser. `opportune desktop` prefers Chrome/Edge/Chromium app mode/maximized and falls back clearly. Preserve old aliases; add `--no-open`, `--browser`, `--host`, `--port`.
- **Likely implementation:** thin handlers in `jobhunt.py`; small `desktop_launcher.py`; keep Uvicorn ownership in `dashapi/server.py`; installed-wheel/platform smoke and mocked browser/process unit tests.
- **Privacy/network:** Loopback default; do not auto-open non-loopback hosts without explicit opt-in; distinguish Opportune from unrelated port owner.
- **Tests:** browser/process mocks; existing Opportune/foreign port; readiness/asset timeout; installed-wheel and manual native-OS launch/cleanup.
- **Dependencies:** release artifact containing prebuilt assets; no native desktop framework.
- **Difficulty / impact:** Medium / high adoption gain.
- **Acceptance:** Released wheel opens a healthy asset-backed dashboard on each supported OS; app-mode fallback is actionable; Ctrl+C cleans up; headless mode is deterministic.

### V1-04 — Approval enforcement is not centralized across all entry points

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** All users; especially users with drafts, inactive/deleted profiles, or schedulers.
- **Evidence:** API routes call `dashapi/server.py:_require_approved_profile`; `jobhunt.py:run_scrape`, `run_smart_scrape`, `pipeline/scheduler.py:run_once`, `pipeline/smart_scrape.py:run_smart_scrape`, and `pipeline/scrape.py:scrape_all` have no visible shared immutable approved-version precondition. `scrape_all` can derive an empty profile ID.
- **Uncertainty:** Static absence does not prove a live unauthorized request occurred; zero-network-call matrix not run.
- **Proposed solution:** `ApprovedProfileContext` service required before source task creation and production ranking; explicit synthetic context only for benchmarks.
- **Technical scope:** new `profile/service.py` or `profile/approval.py`; wire `dashapi/server.py`, `jobhunt.py`, scheduler/smart/scrape/pool and ranking entry points; include profile/version/revision/schema/compiled config.
- **Tests:** missing/draft/inactive/deleted/superseded contexts with lowest source boundary mocked; profile switch and scheduler failure matrix.
- **Privacy/network:** deny before network; do not log compiled private profile fields.
- **Dependencies:** profile-version schema and active-approved pointer.
- **Difficulty / impact:** Medium-high / safety and profile correctness.
- **Acceptance:** API, CLI, smart, scheduler, pool rebuild, agent commands and direct internal calls make zero source calls for missing/draft/inactive/deleted/superseded profiles; switching versions changes ranking context.

### V1-05 — Onboarding is deep but not revision-safe or progressively persisted

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** Users refreshing, pausing, correcting extraction, or editing an approved profile.
- **Evidence:** `onboarding/questions.py:build_questions` covers required groups; `onboarding/store.py:_SCHEMA`, session/answer methods; `frontend/src/onboarding/OnboardingWizard.tsx` keeps interim answers in UI state and submits at review; current `profiles.extracted_json`/`is_active` is mutable JSON-centric state.
- **Proposed solution:** stable profiles plus immutable `profile_versions`, field provenance, durable rejections, draft-linked sessions, revision/ETag auto-save, conflict recovery, explicit approval then activation. Editing approved state creates a new draft.
- **Technical scope:** ordered SQLite tables/migration; draft create/get/patch/analyze/preview/approve and version activation routes; wizard progress/save/review/edit-copy components.
- **Tests:** state transitions, 409 recovery, refresh/restart, approval rollback/immutability, edit-copy and active-context E2E.
- **Privacy/network:** local persistence; remote analysis only after consent; explicit resume retention policy.
- **Dependencies:** migration runner and shared approval context.
- **Difficulty / impact:** High / major completion and trust gain.
- **Acceptance:** Mandatory information remains; every extracted field is editable/rejectable; refresh/restart recovers; stale writes return conflict; approval is atomic and immutable; discovery uses only active approved version.

### V1-06 — Extracted evidence is not fully user-correctable

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** Anyone relying on resume extraction, especially users whose roles, levels, skills, projects or locations are inferred incorrectly.
- **Evidence:** extracted roles/skills/projects/evidence are rendered in `OnboardingWizard.tsx` and typed in `frontend/src/onboarding/types.ts`; a complete provenance-aware field editor/rejection model was not found.
- **Proposed solution:** per-field envelope (`value`, `source`, `evidence`, `confidence`, `status`, `user_modified_at`) and statuses `extracted`, `inferred`, `user_added`, `confirmed`, `rejected`, `needs_review`; durable rejection fingerprints.
- **Technical scope:** `profile_field_values`/`profile_rejections`; provider/service merge logic; provenance editor/restore UI; compatibility import from current extracted JSON.
- **Tests:** all legal/illegal transitions, user confirmation precedence, reject→reanalyze, restore and migration.
- **Privacy/network:** evidence remains local unless explicitly included in a consented provider payload; redact logs/exports.
- **Dependencies:** V1-05 profile versions.
- **Difficulty / impact:** High / ranking quality and user control.
- **Acceptance:** User corrections survive re-analysis and approval; rejected values are not silently reintroduced.

### V1-07 — Freshness preference is hardcoded, not confirmed

- **Severity / classification:** P2 / `Verified` static.
- **Affected users:** Users whose acceptable listing age differs from the hidden seven-day default or who want unknown-date listings handled explicitly.
- **Evidence:** `onboarding/compiler.py` defaults `max_age_days` to seven; `onboarding/questions.py` has no mandatory freshness choice.
- **Proposed solution:** mandatory plain-language freshness section with examples, unknown-date handling and effective-profile preview.
- **Technical scope:** question/field schema, compiler/config, preview UI and freshness policy; migrate current default as an explicit `needs_review` choice when required.
- **Tests:** preset/custom validation, unknown/old/fresh and timezone boundaries, preview/runtime equivalence.
- **Privacy/network:** none beyond existing public listing timestamps.
- **Dependencies:** versioned onboarding draft; benchmark freshness labels.
- **Difficulty / impact:** Low-medium / fewer unexpected exclusions.
- **Acceptance:** Freshness is explicit and preserved in approved profile; unknown date never masquerades as fresh.

### V1-08 — Provider/source privacy and cost labels are incomplete

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** Users selecting local, custom or remote model providers and users enabling external job sources or paid/keyed services.
- **Evidence:** `onboarding/sanitizer.py:sanitize_resume_for_remote`; `onboarding/providers.py`; provider UI in `OnboardingWizard.tsx`; docs in `README.md` and `SECURITY.md`. Warnings exist, but the seven required local/free/key/paid/external-data labels are not consistent across UI/docs.
- **Proposed solution:** shared provider/source capability metadata and pre-send consent. Use exact privacy language: “Profiles, jobs, notes, and application data remain on the user’s machine. Resume analysis can remain fully local. When a user intentionally selects an external model provider, necessary resume content may be sent to that provider after best-effort redaction.”
- **Technical scope:** provider/source metadata schema consumed by settings/onboarding/docs; classify custom endpoints by actual URL; persist consent version/time; expose payload/redaction summary.
- **Tests:** local zero remote calls; remote consent/key; custom local/external endpoint; payload, health, logs and export redaction.
- **Privacy/network:** this finding defines the disclosure boundary; no default remote provider or analytics.
- **Dependencies:** provider settings and onboarding version/consent record.
- **Difficulty / impact:** Medium / informed consent.
- **Acceptance:** Before action users can tell what is local, externally read/sent, keyed, limited or paid; payload/log redaction tests pass.

### V1-09 — Normal-user installation documentation requires contributor tooling

- **Severity / classification:** P1 / `Verified` static.
- **Affected users:** Nontechnical job seekers installing a release and users without Node/npm or repository build knowledge.
- **Evidence:** `README.md` install flow requires Git, uv, Python, Node, `npm ci`, and build; `frontend/dist/` and package data already exist. Isolated wheel served all tested assets successfully.
- **Proposed solution:** primary wheel/sdist with prebuilt assets and release checksums; Node only for contributors/CI; Docker Compose secondary; native wrappers deferred.
- **Technical scope:** README/release workflow/package manifest; isolated install outside checkout; health/onboarding/real-asset smoke; downloadable checksummed artifacts.
- **Tests:** wheel/sdist manifest, both console scripts, no-checkout server/assets, clean OS install and uninstall.
- **Privacy/network:** package manifest excludes personal data; default server remains loopback.
- **Dependencies:** launcher, platform data paths and release workflow.
- **Difficulty / impact:** Medium / major first-run reduction.
- **Acceptance:** clean artifact install and launch outside checkout without Node on each supported OS.

### V1-10 — User data location and database evolution are not release-grade

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** Installed-package users, users upgrading from earlier releases, and users on systems where package directories are read-only or shared.
- **Evidence:** `config.py:PROJECT_ROOT`, `TRACKER_DIR`, `DASHBOARD_DB_PATH`, `CONFIG_PATH`; `dashboard/db.py:init_db`, `_ensure_columns`; `onboarding/store.py` creates a separate schema. No ordered migration IDs/`PRAGMA user_version` flow is present. Installed-path inspection was blocked and remains not run.
- **Proposed solution:** evaluate/adopt `platformdirs`; separate config/data/cache/log/export/backup; ordered transactional SQLite migration runner, previous-release fixtures, backup/integrity/recovery, idempotent legacy `tracker/` migration.
- **Technical scope:** data-path module, `dashboard/migrations.py`-style runner, migration journal/version, DB/store/startup/public-ops integration and legacy relocation report.
- **Tests:** native path contracts, read-only package directory, prior-release/corrupt/interrupted/idempotent migration, counts/foreign keys/integrity and recovery.
- **Privacy/network:** local-only; diagnostics redact paths/usernames and backups use restrictive permissions.
- **Dependencies:** maintainer decision on path roots, wipe/backup policy and migration framework.
- **Difficulty / impact:** High / upgrade and permission reliability.
- **Acceptance:** installed state never defaults beside package code; interrupted migration recovers; active approved profile and all user records survive upgrade.

### V1-11 — Current benchmark cannot support public quality claims

- **Severity / classification:** P1 / `Verified` design gap; current results `Verified` narrow runtime.
- **Affected users:** Job seekers relying on ranking/safety claims and maintainers deciding whether a release is accurate enough to ship.
- **Evidence:** `ranking/fixtures/v1_jobs.json` has 16 cases; `ranking/benchmark.py:QUALITY_GATES`; current output had one Apply→Watch error. No dev/validation/final split, candidate-set P@K, leakage control, role/source segments or confidence intervals.
- **Proposed solution:** implement `BENCHMARK_SPEC.md` full-pipeline candidate-set benchmark with frozen final test, human labels, leakage checks, all requested metrics/segments and deterministic reports.
- **Technical scope:** new `benchmarks/` schemas/datasets/labels/runners/reports; explicit synthetic profile context and no-network replay; raw predictions/config hashes.
- **Tests:** schema/provenance/privacy validation, split leakage/checksum failure, metric denominators/CI/determinism and intentional safety regressions.
- **Privacy/network:** synthetic/permitted snippets only; no real resume, private job history or runtime network.
- **Dependencies:** approved V1 capability matrix, labeling budget and thresholds.
- **Difficulty / impact:** High / evidence for ranking claims.
- **Acceptance:** reproducible no-network benchmark passes agreed global and safety-segment gates; no tuning on final-test examples.

### V1-12 — Source registry size is not source quality

- **Severity / classification:** P1 / `Verified` configured coverage; quality gap `Partially verified`.
- **Affected users:** Users expecting enabled sources to return fresh, live, relevant and affordable listings and maintainers deciding where to expand coverage.
- **Evidence:** `source_registry.yaml` has 71 company entries, 41 enabled (21 Greenhouse, 17 Ashby, 3 Workable). `core/source_health.py:classify_error/cooldown_until_for` records local circuit state with 24-hour blocked/rate-limit and 6-hour server/timeout cooldowns, but `pipeline/scrape.py` and `dashboard/db.py:scrape_runs/job_catalog` lack the complete requested per-source funnel, latency, parsing, cost and retained-result report. `core/link_check.py:verify_job_link` uses verified-TLS HEAD→GET with a 12-second timeout and placeholder/safe-URL checks, but its final GET maps every `HTTPError`—including blocked, rate-limited and server responses—to `dead`; `frontend/src/App.tsx:EvidenceDrawer` hides `dead`/`unreachable` originals.
- **Proposed solution:** normalized `source_runs`, `source_requests`, `source_results`, `listing_observations`, `listing_validation_results`; local report/export and respectful link checks.
- **Technical scope:** ordered tables/repositories, adapter result envelope, scrape/request/normalization/dedupe/ranking/reconciliation instrumentation, CLI/API/dashboard report.
- **Tests:** fixture/live-run separation, every failure category, transaction crash, retained funnel, cost basis, redaction and explicit 200/404/410/401/403/429/5xx/timeout/redirect link cases.
- **Privacy/network:** public source reads only on user run; never store headers/keys/resumes/prompts/full responses; no CAPTCHA/auth bypass.
- **Dependencies:** migration runner, discovery-funnel reason codes and source terms review.
- **Difficulty / impact:** High / rational source investment.
- **Acceptance:** each enabled source reports all requested metrics; only conclusive closure evidence counts closed/dead, while timeout/blocked/rate-limit/auth/server errors remain inconclusive; unknown cost is not reported as zero.

### V1-13 — Local data lifecycle and “wipe” scope are incomplete

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** Privacy-conscious users, users resetting/uninstalling Opportune, and users depending on backups for recovery.
- **Evidence:** `public_ops.py:wipe_local_data` backs up then clears jobs/enrichment/seen state, but static trace does not remove profiles, onboarding/resume state, provider settings/key, config, exports or backups. No restore CLI was identified.
- **Proposed solution:** distinguish export, backup, restore, reset jobs, full local-data wipe, uninstall binaries and backup removal; explicit confirmations and redacted manifest.
- **Technical scope:** `public_ops.py`, CLI/API/settings operations, backup manifest/restore validator, table/file scope registry and platform-data roots.
- **Tests:** exact removed/preserved classes, snapshot/restore rollback, ZIP traversal/symlink/corruption, confirmation and separate backup removal.
- **Privacy/network:** local destructive boundary; no automatic upload; messages/manifests redact private values/paths.
- **Dependencies:** platform data model, ordered migrations and maintainer backup-preservation decision.
- **Difficulty / impact:** Medium-high / privacy and recoverability.
- **Acceptance:** docs/UI match tested scope; full wipe removes every selected class; backup preservation/removal is explicit; restore rejects unsafe archive members.

### V1-14 — Dashboard usefulness is incomplete for empty/partial failure states

- **Severity / classification:** P1 / `Partially verified`.
- **Affected users:** Users with zero, few, partially failed, stale or all-excluded discovery results.
- **Evidence:** `frontend/src/App.tsx`, `frontend/src/api.ts`, `dashapi/server.py`, `dashboard/db.py` provide profiles, filters, actions and quality summary, but source funnel and actionable zero-result reason are absent.
- **Proposed solution:** first-zero-stage display, effective search profile, source failures/last success, freshness/link uncertainty and Ready/Review/Excluded explanation consistency.
- **Technical scope:** `frontend/src/App.tsx`/API types, server status/scrape routes, source/funnel DB reads and profile draft-edit link.
- **Tests:** empty/partial/all-excluded/success states, action persistence/reload, reason contradictions, browser E2E and accessibility.
- **Privacy/network:** show effective rules safely without resume evidence, keys, prompts or full source errors.
- **Dependencies:** V1-02 funnel, V1-12 source metrics and versioned edit-copy flow.
- **Difficulty / impact:** Medium / user trust and recovery.
- **Acceptance:** users know what to do next and why each bucket/result limitation exists.

### V1-15 — Accessibility is not release-evidenced

- **Severity / classification:** P2 / `Partially verified` static; runtime `Requires runtime testing`.
- **Affected users:** Keyboard-only, screen-reader, low-vision, motion-sensitive and zoom/reflow users.
- **Evidence:** focus/semantic styles exist in `frontend/src/index.css` and onboarding CSS, but repository inventory found no frontend test/spec files or configured axe-equivalent E2E suite; `App.tsx` and wizard need keyboard/progress/live-region/dialog/error review.
- **Proposed solution:** component/browser test harness, automated accessibility checks, keyboard checklist, semantic progress/errors, focus management, reduced motion, contrast and zoom/reflow evidence.
- **Technical scope:** minimal frontend test configuration/dependencies; App/wizard/CSS fixes and versioned manual checklist tied to release artifact.
- **Tests:** keyboard-only, focus/dialog, screen-reader names/progress/errors/live regions, 200% zoom, 320px reflow, contrast and reduced motion.
- **Privacy/network:** synthetic local fixtures; accessibility logs/screenshots must not contain private resumes/jobs.
- **Dependencies:** maintainer approval for minimal test dependencies and stable onboarding/dashboard components.
- **Difficulty / impact:** Medium / inclusive use and release confidence.
- **Acceptance:** no serious/critical automated violations and manual keyboard flow passes on release artifact.

### V1-16 — Cross-platform support claim exceeds evidence

- **Severity / classification:** P1 / `Verified` evidence gap.
- **Affected users:** Native Windows, macOS and Linux users choosing Opportune based on package metadata/support claims.
- **Evidence:** `pyproject.toml` declares OS Independent; `.github/workflows/ci.yml` runs Ubuntu only. Current installed smoke ran under WSL/Linux; no native Windows/macOS artifact evidence exists.
- **Proposed solution:** artifact-backed matrix for Windows 11 x64, Ubuntu 22.04/24.04 x64, and current/previous supported macOS; WSL/Docker separately labeled.
- **Technical scope:** platform smoke workflow/manual evidence template covering install, launch, upload, onboarding, approved discovery, scheduler, backup/export/wipe, upgrade and uninstall/retention.
- **Tests:** exact released checksum on each OS/version/architecture; URLs/assets/ports/data locations/migrations and cleanup.
- **Privacy/network:** use synthetic profiles/listings for automated platform runs; keep credentials absent.
- **Dependencies:** packaged launcher, state migration, lifecycle commands and release artifact.
- **Difficulty / impact:** High / truthful compatibility.
- **Acceptance:** only tested OS/version/architecture combinations are called supported; install/onboarding/discovery/backup/wipe/upgrade/uninstall evidence is dated and checksummed.

### V1-17 — Public release/documentation state is inconsistent

- **Severity / classification:** P2 / `Verified`.
- **Affected users:** New users, contributors, package consumers and maintainers trying to determine current release/support status.
- **Evidence:** public unarchived GitHub repository; `v0.1.0` tag at `ad8a21f`; no GitHub Release object; `main` at `b24d49e`; README/ROADMAP/PUBLIC_RELEASE/CHANGELOG status wording differs. Latest `main` CI run `29612150267` succeeded.
- **Proposed solution:** one version/status vocabulary; reconcile docs/tag/package/release; publish artifacts/checksums only after gates pass.
- **Technical scope:** README/ROADMAP/CHANGELOG/PUBLIC_RELEASE/MAINTAINING/metadata/release workflow and link/status checker.
- **Tests:** docs path/link/version claims, package/API/assets version agreement and remote release-object verification.
- **Privacy/network:** public docs/artifacts only; package manifest and secret scan required.
- **Dependencies:** final support/capability decisions and release scorecard pass.
- **Difficulty / impact:** Low-medium / contributor/user trust.
- **Acceptance:** all public surfaces agree on alpha/V1 support and evidence.

### V1-18 — No local pilot measurement workflow

- **Severity / classification:** P1 / `Partially verified` static absence.
- **Affected users:** Real job seekers whose installation, onboarding, relevance, trust and privacy outcomes are otherwise unmeasured; maintainers prioritizing V1 work.
- **Evidence:** no pilot event store, consent workflow, inspectable anonymized export or survey flow found in current schema/CLI/API/content search.
- **Proposed solution:** opt-in local events and ratings, inspection/deletion, user-triggered sanitized JSON export, no upload destination.
- **Technical scope:** pilot sessions/events/ratings/exports tables, consent setting, local report API/CLI/UI, allowlisted schema and export validator.
- **Tests:** off by default, opt-in/out/retention/deletion, all 18 metrics, prohibited-field scans and exact preview/export.
- **Privacy/network:** no automatic sender; exclude identity/resume/job URLs/notes/keys/prompts/responses/paths.
- **Dependencies:** pilot protocol approval, stable launch/onboarding/discovery/dashboard events and migration runner.
- **Difficulty / impact:** High / real-user validation.
- **Acceptance:** all requested pilot metrics are derivable or explicitly rated; export contains no identity/resume/job URLs/notes/keys/prompts/paths.

### V1-19 — Release artifacts include resume/profile example files that need privacy/provenance review

- **Severity / classification:** P1 / `Verified` package membership; sensitivity `Requires runtime testing`/maintainer review.
- **Affected users:** Everyone downloading the artifact and any person whose real or identifying profile data could have been used to create bundled examples.
- **Evidence:** `pyproject.toml:[tool.setuptools.data-files]` includes `candidate_profile.yaml`, `resume/resume.txt`, and `resume/resume_profile.md`; `uv build` copied these into sdist/wheel. This audit intentionally did not inspect private resume content.
- **Proposed solution:** remove candidate-specific artifacts from package unless demonstrably synthetic and necessary; replace with clearly synthetic examples, provenance notice and package-content regression test.
- **Technical scope:** `pyproject.toml` data-file allowlist, synthetic examples/provenance, wheel/sdist manifest and release secret/personal-pattern scan.
- **Tests:** exact manifest, install/assets after removal, prohibited personal/secret patterns and source-vs-artifact comparison.
- **Privacy/network:** prevents unnecessary profile/resume distribution; no network change.
- **Dependencies:** maintainer content/provenance review before deletion/replacement.
- **Difficulty / impact:** Low-medium / privacy and package hygiene.
- **Acceptance:** released artifacts contain no personal resume/profile data; exact manifest is reviewed and checked automatically.

### V1-20 — Security release evidence is incomplete

- **Severity / classification:** P1 / `Requires runtime testing` plus existing-control trace.
- **Affected users:** All users, particularly those uploading resumes, opening external listings, backing up/restoring data or recovering from database errors.
- **Evidence:** controls exist in resume readers/sanitizer, `core/http.py`, link handling, FastAPI routes and backup code, but no complete named matrix currently proves traversal/oversize/deceptive file, stored script/unsafe URL, host/origin, secret diagnostics, ZIP restore, symlink, corrupt DB and interrupted migration behavior.
- **Proposed solution:** named unit/API/browser/installed-artifact cases in a security test directory; fail closed with bounded resource use and redacted messages.
- **Technical scope:** `tests/security/` cases against server/resume parser/http/link/public ops/migrations and frontend external-link rendering; patch production controls only where tests reveal gaps.
- **Tests:** traversal, size/MIME/malformed/parser abuse, HTML/script/schemes, host/origin, secret/path diagnostics, ZIP/symlink/wipe, corrupt/interrupted DB.
- **Privacy/network:** synthetic secrets/resumes/listings; no live hostile probes or external upload.
- **Dependencies:** restore/migration implementations for their cases; security failures block release.
- **Difficulty / impact:** Medium-high / release trust.
- **Acceptance:** no path escape, script execution, unsafe state mutation, secret disclosure, ambiguous destructive wipe, inconsistent backup or unrecoverable migration corruption.

## Capability matrix requiring maintainer decision

| Area | Current evidence-based state | V1 recommendation |
|---|---|---|
| Applied AI / LLM / AI engineering | Implemented deterministic terms and tuned fixtures; not broadly benchmarked | Primary supported recommendation family after new benchmark passes |
| General AI/ML engineering | Classification/ranking logic exists; segment quality unmeasured | Supported only after segment gate |
| Software engineering | Some title handling; current logic is AI-focused | Classification/negative examples until benchmark supports recommendation |
| Data engineering | Some title/skill handling; unmeasured | Classification/negative examples until benchmark supports recommendation |
| Product / analytics | Current fixtures often treat plain analytics as negative | Do not claim recommendation support in V1 without deliberate design/benchmark |
| New grad / entry / junior | Current primary intent | Supported after benchmark/pilot gates |
| Mid-level | Some current candidates/classification | Review/support only after profile-level benchmark |
| Senior | Primarily negative for early-career profiles | Supported as correct exclusion/Review evidence, not positive target by default |
| U.S. remote/hybrid/onsite | Rules exist; compact-input defect verified | Block release until canonicalization and segment tests pass |
| Sponsorship/authorization | Deterministic gates exist | Hard safety segment; ambiguous language must abstain to Review |

## Privacy statement for all V1 documents and UI

> Profiles, jobs, notes, and application data remain on the user’s machine. Resume analysis can remain fully local. When a user intentionally selects an external model provider, necessary resume content may be sent to that provider after best-effort redaction.

Do not claim complete network isolation: enabled job sources read public data externally, and selected remote model providers receive necessary redacted resume content.

## What was not tested

- No live job-source request was initiated during this audit.
- No native Windows or macOS install/launch/migration run.
- No browser accessibility, screen-reader, contrast or full keyboard pass.
- No destructive full-wipe/restore or interrupted-migration test.
- No external-provider payload/log security run.
- No real-user onboarding/relevance/privacy pilot.
- No final public benchmark dataset exists yet.
- Installed package data path was not inspected after the environment denied that command; it remains unverified.

## Release recommendation

Do not add Version 2 email/outreach/application-evidence features. First fix V1-01/V1-02, add V1-03, close the approval/data/privacy blockers, publish benchmark/source evidence, and run the pilot. Release readiness must be determined only from `RELEASE_SCORECARD.md`; blank evidence is failure, not “done.”
