# Opportune Version 1 Contributor Backlog

## Backlog evidence

At audit time, GitHub returned no Issues and two open Dependabot PRs (`#7`, `#8`) unrelated to these proposals. Repository symbol/test searches were used to distinguish existing partial controls from missing V1 outcomes. Re-check Issues/PRs immediately before creating tickets.

Labels are proposals. No GitHub Issues were created by this audit.

## 1. Canonicalize onboarding location preferences

- **Label:** `type:bug`, `area:onboarding`, `area:ranking`, `priority:P1`
- **Classification/evidence:** `Verified`; `onboarding/compiler.py:compile_search_config`, `ranking/guardrails.py:location_verdict`; sanitized runtime funnel 6,494 catalog → 24 role → 0 location; canonical replay → 19 combined.
- **Difficulty:** Medium.
- **User problem:** Equivalent U.S. input can produce an empty dashboard.
- **Technical scope:** shared strict normalizer with display/canonical kind/code; compiler/guard/query use; onboarding confirmation; ordered migration for recognized aliases; ambiguity `needs_review`.
- **Likely files:** new `profile/normalization.py`; compiler/questions/guardrails/query strategy; wizard; migration; tests.
- **Tests:** alias/property/unit; compiler/guard consistency; migration idempotency; end-to-end sanitized fixture.
- **Privacy/network:** local only; do not log original private profile fields.
- **Acceptance:** equivalent aliases behave identically; ambiguous values never broaden silently; deterministic compatible jobs become visible.
- **Dependencies/non-goals:** migration runner helpful; no fuzzy worldwide geocoder.

## 2. Add discovery-funnel diagnostics and zero-result recovery

- **Label:** `type:feature`, `area:pipeline`, `area:dashboard`, `priority:P1`
- **Classification/evidence:** `Partially verified`; current complete funnel required custom inspection; `pipeline/scrape.py`, `dashapi/server.py`, `frontend/src/App.tsx`.
- **Difficulty:** Medium.
- **User problem:** Empty/partial results do not explain where listings disappeared.
- **Technical scope:** versioned stage counts/reason codes, per-source breakdown, API/status, `opportune diagnose discovery --json`, actionable empty state/edit-copy link.
- **Likely files:** scrape, DB source tables, server, jobhunt, App/API types, tests.
- **Tests:** first-zero fixture per stage; redaction; partial source failure; UI E2E.
- **Privacy/network:** counts/reasons only; no resume/key/raw prompt/full job/path.
- **Acceptance:** every zero-result run identifies first zero and safe corrective action; no safety relaxation.
- **Dependencies:** location normalization and source vocabulary.

## 3. Add `opportune run` and `opportune desktop`

- **Label:** `type:feature`, `area:cli`, `area:release`, `priority:P1`
- **Classification/evidence:** `Verified`; both console scripts exist, but `opportune run` exits 2 and current `cmd_dashboard` only prints URL/runs Uvicorn.
- **Difficulty:** Medium.
- **User problem:** Users must copy a URL and cannot request desktop-like app mode.
- **Technical scope:** health/asset readiness, attach/port ownership, default browser/app mode/fallback, loopback safety, `--no-open`.
- **Likely files:** `jobhunt.py`, new `desktop_launcher.py`, server/release docs/tests.
- **Tests:** mocked browser/process; health timeout; foreign port; installed wheel; manual supported OS.
- **Privacy/network:** loopback default; no external URL opening by default.
- **Acceptance:** one installed command opens healthy packaged dashboard; app-mode fallback is clear; Ctrl+C cleans up.
- **Dependencies:** existing wheel/frontend-asset smoke and supported-OS release matrix.
- **Non-goal:** Tauri/Electron/native shell.

## 4. Introduce immutable `ApprovedProfileContext`

- **Label:** `type:architecture`, `area:safety`, `priority:P1`
- **Classification/evidence:** `Partially verified`; API guard exists but no shared lowest-boundary context across CLI/scheduler/internal paths.
- **Difficulty:** Medium-high.
- **User problem:** Discovery/ranking may not consistently use the explicitly approved active profile.
- **Technical scope:** domain service returning profile/version/revision/schema/compiled config; explicit synthetic benchmark context.
- **Likely files:** new `profile/service.py` or `approval.py`; server/jobhunt/scheduler/scrape/smart/pool/ranking.
- **Tests:** all invalid profile states; context switch; no fallback.
- **Privacy/network:** resolve before source task creation.
- **Acceptance:** every production entry point requires one immutable active approved context.
- **Dependencies:** profile-version schema.

## 5. Prove zero source calls for unapproved discovery entry points

- **Label:** `type:test`, `area:safety`, `priority:P1`, `good-first-test`
- **Classification/evidence:** `Partially verified`; static gap in CLI/scheduler/smart paths.
- **Difficulty:** Medium.
- **User problem:** Approval gate cannot be trusted without boundary tests.
- **Technical scope:** integration matrix patching lowest HTTP/source boundary for API, CLI, smart, scheduler once/recurring, pool rebuild, agent commands and direct scrape.
- **Likely files:** onboarding, agent CLI, scheduler, pipeline execution tests.
- **Tests:** the issue itself; assert zero calls and bounded recorded error.
- **Privacy/network:** tests must be fully offline.
- **Acceptance:** missing/draft/inactive/deleted/superseded states all deny before network.
- **Dependencies:** Issue 4 implementation.

## 6. Add ordered SQLite migration runner

- **Label:** `type:feature`, `area:database`, `priority:P1`
- **Classification/evidence:** `Partially verified`; `dashboard/db.py:init_db/_ensure_columns` uses schema plus presence-based ALTER; onboarding schema is separate.
- **Difficulty:** High.
- **User problem:** Upgrades lack explicit ordered/rollback evidence.
- **Technical scope:** migration IDs/`PRAGMA user_version` or journal, transactions, backup, integrity/foreign-key/count validation, interruption recovery, previous-release fixtures.
- **Likely files:** new `dashboard/migrations.py`, DB/store startup, tests/fixtures.
- **Tests:** each previous release, idempotency, corrupt/interrupted/retry, destructive table-copy migration.
- **Privacy/network:** local data only; backups permission-safe.
- **Acceptance:** no silent destructive change; source DB recoverable after every failure.
- **Dependencies:** previous-release fixture policy and maintainer approval of the lightweight runner design.
- **Non-goal:** Alembic unless ORM/branching need is demonstrated.

## 7. Move user state to platform-standard directories

- **Label:** `type:feature`, `area:installation`, `priority:P1`
- **Classification/evidence:** `Partially verified`; `config.py` derives project/module-relative paths; installed path inspection remains not run.
- **Difficulty:** High.
- **User problem:** Installed package may write to unsuitable/unwritable locations.
- **Technical scope:** evaluate/adopt `platformdirs`; separate config/data/cache/log/export/backup; legacy tracker dry-run/backup/copy/verify/atomic switch/idempotency.
- **Likely files:** config/data-path module, public ops, server/CLI startup, migrations/tests/docs.
- **Tests:** Windows/macOS/Linux path contracts; permissions; migration/recovery.
- **Privacy/network:** protect local files and avoid leaking paths in diagnostics.
- **Acceptance:** package modules/assets are read-only; user data survives upgrade and old data remains until verified.
- **Dependencies:** ordered migration runner.

## 8. Add immutable profile versions and active approved pointer

- **Label:** `type:feature`, `area:onboarding`, `area:database`, `priority:P1`
- **Classification/evidence:** `Proposal` based on mutable JSON current state.
- **Difficulty:** High.
- **User problem:** Editing/activation boundaries are not version-auditable.
- **Technical scope:** `profiles`, `profile_versions`, `profile_field_values`, `profile_rejections`, draft-linked sessions, one active approved pointer.
- **Likely files:** DB/store/service/server/profile modules and migrations.
- **Tests:** immutability, transaction approval, edit-copy, activation constraints, profile switch.
- **Privacy/network:** explicit resume retention policy; fields remain local.
- **Acceptance:** approved rows immutable; edits create draft; discovery uses one active approved version.
- **Dependencies:** Issues 6–7.

## 9. Add revision-safe onboarding auto-save and resume

- **Label:** `type:feature`, `area:onboarding`, `area:frontend`, `priority:P1`
- **Classification/evidence:** `Partially verified`; wizard interim state is not progressively server-saved.
- **Difficulty:** Medium-high.
- **User problem:** Long onboarding can be lost or conflict across refresh/session.
- **Technical scope:** draft GET/PATCH, expected revision/ETag, idempotent operations, 409 latest-state payload, save indicator/retry/resume.
- **Likely files:** store/service/server/API client/wizard/types/tests.
- **Tests:** refresh/restart, concurrent edits, network failure/retry, false-saved prevention.
- **Privacy/network:** local API only; no analytics.
- **Acceptance:** latest acknowledged revision survives; conflicts are user-resolvable without loss.
- **Dependencies:** profile versions.

## 10. Add provenance-aware extraction editor and durable rejection

- **Label:** `type:feature`, `area:onboarding`, `priority:P1`
- **Classification/evidence:** `Partially verified`; extraction is shown but full field envelope/rejection flow absent.
- **Difficulty:** High.
- **User problem:** Users cannot reliably correct/reject all inferred roles/skills/evidence.
- **Technical scope:** field envelope/status transitions, evidence/confidence, reject/restore, analysis merge respecting fingerprints.
- **Likely files:** providers/compiler/service/store/wizard/types/tests.
- **Tests:** all transitions; reject→reanalyze; user confirmation precedence; migration.
- **Privacy/network:** minimize evidence sent externally; redact logs.
- **Acceptance:** all extracted fields correctable; rejected values do not reappear silently.
- **Dependencies:** profile versions.

## 11. Make freshness a mandatory confirmed preference

- **Label:** `type:feature`, `area:onboarding`, `area:ranking`, `difficulty:small`
- **Classification/evidence:** `Verified`; compiler hardcodes seven days and questions omit choice.
- **Difficulty:** Low-medium.
- **User problem:** Listings can disappear under an unseen default.
- **Technical scope:** presets/custom days, unknown-date policy, preview and approved field.
- **Likely files:** questions/compiler/wizard/freshness tests.
- **Tests:** boundaries/timezone/unknown/custom validation.
- **Privacy/network:** none.
- **Acceptance:** no hidden default; unknown date is explicit.
- **Dependencies:** versioned onboarding fields and benchmark freshness labels.

## 12. Add provider/source disclosure metadata and consent

- **Label:** `type:feature`, `area:privacy`, `priority:P1`
- **Classification/evidence:** `Partially verified`; warning/sanitizer exist, labels are inconsistent.
- **Difficulty:** Medium.
- **User problem:** User cannot reliably tell what leaves machine or costs money.
- **Technical scope:** shared seven-label capability metadata, actual URL/local classification, pre-send consent, payload/redaction summary.
- **Likely files:** providers/service/wizard/settings/README/SECURITY/tests.
- **Tests:** local zero calls; remote consent; custom endpoint; redaction/diagnostics.
- **Privacy/network:** central purpose of issue.
- **Acceptance:** exact approved privacy text and labels appear before action.
- **Dependencies:** shared provider metadata and versioned consent record.

## 13. Implement restore and complete data-lifecycle scopes

- **Label:** `type:feature`, `area:privacy`, `area:operations`, `priority:P1`
- **Classification/evidence:** `Partially verified`; backup/reset exists; wipe omits profiles/settings/etc.; restore not found.
- **Difficulty:** Medium-high.
- **User problem:** “Wipe” can be misunderstood and backup cannot be proven restorable.
- **Technical scope:** inspect/export/backup/restore/reset jobs/full wipe/uninstall; manifests and separate backup-removal confirmation.
- **Likely files:** `public_ops.py`, `jobhunt.py`, server/settings UI, tests/docs.
- **Tests:** exact scope, consistent snapshot, ZIP traversal/symlink, corrupt archive, restore rollback.
- **Privacy/network:** local destructive boundary; explicit confirmation.
- **Acceptance:** command/UI/docs match tested removed/preserved classes.
- **Dependencies:** platform data paths, ordered migrations and maintainer backup-preservation decision.

## 14. Harden release package manifest and remove candidate-specific data

- **Label:** `type:bug`, `area:packaging`, `area:privacy`, `priority:P1`
- **Classification/evidence:** `Verified` membership; sensitivity unverified. Wheel/sdist include candidate profile and resume/profile files.
- **Difficulty:** Low-medium.
- **User problem:** Release may ship unnecessary candidate-specific artifacts.
- **Technical scope:** replace/remove with clearly synthetic fixtures; manifest allowlist; wheel/sdist content test.
- **Likely files:** `pyproject.toml`, sample files, release tests/docs.
- **Tests:** manifest has required assets/config only; secret/personal-pattern scan.
- **Privacy/network:** prevents package disclosure.
- **Acceptance:** maintainer-reviewed artifact contains no personal resume/profile data.
- **Dependencies:** maintainer content/provenance review and installed-artifact manifest test.

## 15. Create public benchmark schemas and scenario dataset

- **Label:** `type:feature`, `area:evaluation`, `priority:P1`
- **Classification/evidence:** `Proposal`; current 16 fixtures are insufficient.
- **Difficulty:** High.
- **User problem:** Ranking claims are not independently auditable.
- **Technical scope:** `BENCHMARK_SPEC.md` tree/schemas, eight profile strata/four ten-listing sets, 320 derived judgments unless capability changes, provenance, labels and manifests.
- **Likely files:** new `benchmarks/` schemas/datasets/labels/readme.
- **Tests:** schema/provenance/private-data validation.
- **Privacy/network:** synthetic/permitted text only; no real resumes.
- **Acceptance:** all scenario cells and requested labels represented with documented count formula.
- **Dependencies:** capability decision and labeling budget.

## 16. Add benchmark split/leakage/metric/report runner

- **Label:** `type:feature`, `area:evaluation`, `priority:P1`
- **Classification/evidence:** `Proposal`.
- **Difficulty:** High.
- **User problem:** Final-test contamination and aggregate metrics can hide unsafe segments.
- **Technical scope:** cluster split, hashes/similarity, frozen checksums, no-network run, all metrics/segments/CI/raw predictions/gates.
- **Likely files:** `benchmarks/runners/*`, CI, tests.
- **Tests:** intentional leaks, checksum change, denominator/segment edge cases, determinism.
- **Privacy/network:** runner disables network.
- **Acceptance:** clean checkout reproduces report; final test cannot be tuned silently.
- **Dependencies:** Issue 15.

## 17. Add normalized source-quality storage and instrumentation

- **Label:** `type:feature`, `area:sources`, `area:database`, `priority:P1`
- **Classification/evidence:** `Partially verified` gap.
- **Difficulty:** High.
- **User problem:** Cannot know which sources produce useful current jobs.
- **Technical scope:** `source_runs`, `source_requests`, `source_results`, `listing_observations`, `listing_validation_results`; adapter envelopes and funnel.
- **Likely files:** migrations, DB repositories, source health, scrape/adapters, API/CLI tests.
- **Tests:** request/parse/empty/circuit/partial outcomes; transaction crash; retention/redaction.
- **Privacy/network:** no headers/keys/full responses/resume/prompts.
- **Acceptance:** all 15 source metrics derivable per enabled source.
- **Dependencies:** migration runner and funnel vocabulary.

## 18. Add responsible cached link/lifecycle validation

- **Label:** `type:feature`, `area:sources`, `area:safety`
- **Classification/evidence:** `Verified` static defect plus runtime gap; `core/link_check.py:verify_job_link` uses safe URL/TLS/placeholder checks and HEAD→GET, but any final GET `HTTPError` becomes `dead`; `frontend/src/App.tsx:EvidenceDrawer` hides dead/unreachable originals. Live behavior remains unmeasured.
- **Difficulty:** Medium.
- **User problem:** Dead/closed links reduce trust; blocked/timeouts can be misclassified.
- **Technical scope:** TTL, bounded concurrency/time/retry/redirect, respectful user agent, conclusive/inconclusive categories, source reconciliation preference.
- **Likely files:** `core/link_check.py`, source health/DB, adapters/tests.
- **Tests:** 200/404/410/redirect/timeout/401/403/429/5xx/block/TLS; assert only conclusive closure becomes dead and no CAPTCHA bypass occurs.
- **Privacy/network:** public URLs only; terms review.
- **Acceptance:** blocked/timeout/auth never confirmed closed; Ready has no confirmed-closed links in release sample.
- **Dependencies:** source-quality storage, normalized link-state taxonomy and per-domain policy review.

## 19. Improve dashboard empty/partial/source/evidence states

- **Label:** `type:feature`, `area:dashboard`, `priority:P1`
- **Classification/evidence:** `Partially verified`.
- **Difficulty:** Medium.
- **User problem:** User cannot understand no/few results, source failure or decisive evidence.
- **Technical scope:** funnel, last success/failures, source/freshness/link uncertainty, effective profile, Ready/Review/Excluded reason consistency.
- **Likely files:** App/API/server/DB/CSS/tests.
- **Tests:** empty/partial/all-excluded states, persistence/reload, E2E/accessibility.
- **Privacy/network:** redact diagnostics.
- **Acceptance:** user can identify cause/next action and trust bucket explanation.
- **Dependencies:** Issues 2 and 17.

## 20. Add frontend component/E2E accessibility release harness

- **Label:** `type:test`, `area:accessibility`, `priority:P2`
- **Classification/evidence:** `Verified` test gap; no conventional frontend test/spec files.
- **Difficulty:** Medium.
- **User problem:** Keyboard/screen-reader/accessibility regressions are not release-gated.
- **Technical scope:** minimal component/browser toolchain, axe-equivalent checks, keyboard checklist, focus/error/progress/live-region/zoom/reduced-motion/contrast cases.
- **Likely files:** frontend package/config/tests, App/wizard/CSS.
- **Tests:** issue scope.
- **Privacy/network:** synthetic local fixtures.
- **Acceptance:** no serious/critical automated violations and manual keyboard checklist passes.
- **Dependencies:** maintainer approval for the minimal frontend test toolchain and stable onboarding/dashboard routes.

## 21. Add opt-in local pilot event store and anonymized export

- **Label:** `type:feature`, `area:pilot`, `area:privacy`, `priority:P1`
- **Classification/evidence:** `Proposal`; current pilot workflow not found.
- **Difficulty:** High.
- **User problem:** Real installation/onboarding/relevance/trust outcomes are unknown.
- **Technical scope:** consented local sessions/events/ratings, inspect/delete, allowlist, report/export validator, no uploader.
- **Likely files:** migrations, pilot store/service/API/CLI/UI/tests.
- **Tests:** off by default, opt-in/out, prohibited field scans, deletion/export preview.
- **Privacy/network:** no automatic network; strict banned fields.
- **Acceptance:** all `PILOT_TEST_PLAN.md` metrics derivable; export has zero prohibited data.
- **Dependencies:** migration runner, stable product event vocabulary and approved consent/retention policy.

## 22. Add concrete V1 security test matrix

- **Label:** `type:test`, `area:security`, `priority:P1`
- **Classification/evidence:** `Requires runtime testing`.
- **Difficulty:** Medium-high.
- **User problem:** Security/privacy claims lack route-level evidence.
- **Technical scope:** resume traversal/size/MIME/parser bounds; listing script/URL; host/origin; secret/path diagnostics; backup/restore/wipe/symlink; corrupt/interrupted DB.
- **Likely files:** `tests/security/*`, server/resume/http/link/public ops as failures reveal.
- **Tests:** issue scope across unit/API/browser/installed artifact.
- **Privacy/network:** use synthetic secrets/private data and offline fixtures.
- **Acceptance:** all release security gates pass with no unsafe partial state.
- **Dependencies:** restore and migration implementations for their cases; any discovered P0 blocks release.

## 23. Reconcile release docs and add artifact-backed OS matrix

- **Label:** `type:documentation`, `area:release`, `priority:P2`
- **Classification/evidence:** `Verified`; public repo/tag exists, no GitHub Release, docs differ, CI Ubuntu-only.
- **Difficulty:** Medium.
- **User problem:** Users cannot tell actual alpha/support/install state.
- **Technical scope:** one status/version vocabulary; release workflow/checksums; Windows/macOS/Ubuntu clean install/launch/onboarding/upgrade/uninstall matrix; WSL/Docker separate.
- **Likely files:** README/ROADMAP/CHANGELOG/PUBLIC_RELEASE/MAINTAINING/workflows.
- **Tests:** link/path/status checks; artifact smoke per OS.
- **Privacy/network:** release artifacts/manifests only.
- **Acceptance:** every claim maps to dated checksummed evidence; unsupported platforms are not advertised.
- **Dependencies:** launcher/package/data migration and scorecard gates.
