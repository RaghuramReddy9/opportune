# Opportune Version 1 Release Scorecard

**Candidate basis:** the commit containing this scorecard on `codex/v1-1-release-consolidation`, prepared from `main` at `3171b287ff788a268f58fb99526e7b87dafed1e9`.

**Assessment date:** 2026-07-20

**Current decision:** **NO-SHIP for a public Version 1 release.** The implementation and automated native-OS candidate matrix are verified, but the governed public benchmark and human pilot have not run, accessibility evidence is incomplete, and no release artifact has been approved or published.

## Status and evidence rules

- `PASS`: the exact local gate was executed successfully on this working tree.
- `FAIL`: a required release condition is known to be unmet.
- `NOT RUN`: the gate requires evidence that has not been produced.
- `WAIVED`: requires a named owner, rationale, and expiry; safety/privacy/destructive-data gates are non-waivable.

Evidence classes used below:

- `Verified`
- `Partially verified`
- `Requires runtime testing`
- `Proposal`
- `Not reproduced`

## 1. Current local verification

| Gate | Status | Evidence class | Evidence |
|---|---|---|---|
| Backend suite | PASS | Verified | `uv run python -m pytest tests -q` → 355 passed, 5 subtests passed in 60.19s |
| Python lint | PASS | Verified | `uv run ruff check .` → clean |
| Diff whitespace | PASS | Verified | `git diff --check` → clean |
| Frontend build | PASS | Verified | Vite production build, 1,778 modules |
| Frontend lint | PASS | Verified | oxlint: 0 warnings/errors |
| Frontend production dependency audit | PASS | Verified | `npm audit --omit=dev --audit-level=high` → 0 vulnerabilities |
| Python runtime dependency audit | PASS | Verified | `pip-audit` → no known vulnerabilities; local `opportune` package skipped because it is not on PyPI |
| Wheel and sdist | PASS | Verified | both rebuilt from the current tree |
| Wheel/sdist package privacy | PASS | Verified | no `candidate_profile.yaml`, `resume.txt`, or `resume_profile.md` in either archive |
| Installed wheel smoke | PASS | Verified | isolated uv environment outside checkout; CLI aliases, server readiness, health, HTML/assets, doctor, backup, export, and clean shutdown |
| Artifact checksums | PASS | Verified | generated for every local/native candidate build and retained with that build's artifacts; no source-controlled hash is labeled as a release checksum |

These checks are local evidence only. Checksums change whenever the tree is rebuilt and are not release checksums until a commit is frozen and maintainer-approved.

## 2. Useful-listing and diagnosis gates

| Gate | Status | Evidence class | Evidence / limitation |
|---|---|---|---|
| Compact U.S. aliases normalize safely | PASS | Verified | Shared onboarding/query/guardrail tests; unknown custom values remain explicit and deterministic |
| Existing malformed profile migration | PASS | Verified | Legacy/profile-version migration fixtures; no live approved profile was mutated |
| Read-only canonical retained-data replay | PASS | Partially verified | 6,494 active rows → 19 role/location pool candidates after canonical U.S. interpretation |
| Versioned discovery funnel | PASS | Verified | one schema shared by pipeline, persistence, API, CLI, and UI |
| Actionable true-empty state | PASS | Verified | UI separates no underlying jobs from filter-hidden jobs; includes effective profile and rerun/settings actions |
| Fresh useful live listings | NOT RUN | Requires runtime testing | No live source request was authorized during implementation |
| Human top-5/top-10 relevance | NOT RUN | Requires runtime testing | Requires governed benchmark and pilot evidence |
| Unsafe Ready result | NOT RUN | Requires runtime testing | Must be zero in governed final test and pilot |

## 3. Installation and launch

| Gate | Status | Evidence class | Evidence / limitation |
|---|---|---|---|
| Normal user needs no Node/source checkout | PASS | Verified | isolated wheel serves prebuilt assets |
| `opportune run --no-open` | PASS | Verified | installed-wheel smoke |
| `opportune desktop` app-mode/fallback | PASS | Verified | focused launcher contracts; this is browser app-mode, not a native app |
| Readiness and clean shutdown | PASS | Verified | bounded readiness and process lifecycle tests; browser verification server shut down cleanly |
| Existing Opportune instance | PASS | Verified | focused launcher tests |
| Foreign occupied port | PASS | Verified | focused launcher tests |
| Loopback/non-loopback safety | PASS | Verified | loopback default; explicit opt-in required for non-loopback browser opening |
| Platform-standard writable state | PASS | Verified | path/lifecycle tests and installed-artifact smoke passed on Linux, Windows 2022, and macOS 14/15 |
| Native Windows/macOS launch | PASS | Verified | `run --no-open`, readiness, health, assets, and clean shutdown passed in the release-candidate matrix |
| GitHub Release/checksums | FAIL | Requires runtime testing | local wheel, sdist, SHA256SUMS, and manifest pass; no maintainer-approved release object exists |

## 4. Onboarding, approval, and profile versions

| Gate | Status | Evidence class | Evidence / limitation |
|---|---|---|---|
| Mandatory onboarding answers | PASS | Verified | compiler/service/API regressions pass |
| Draft save/resume | PASS | Verified | durable onboarding session tests |
| Field provenance/status metadata | PASS | Verified | value, source, evidence, confidence, status, user-modified timestamp; rejected inferred values retained as rejected |
| User answers remain authority | PASS | Verified | focused compiler/location tests |
| Immutable approved profile | PASS | Verified | edits create drafts; active approved snapshot remains unchanged |
| Atomic approval/activation | PASS | Verified | transactional version tests; previous approved version becomes superseded |
| Legacy active-profile backfill | PASS | Verified | active historical profiles become approved version 1 rather than draft |
| Version API | PASS | Verified | list versions, create draft, approve version |
| Approved-profile enforcement | PASS | Verified | scrape, scheduler, and catalog materialization fail closed |
| Zero source calls without approval | PASS | Verified | explicit mocked source-network boundary test |
| Full interactive correction UX | NOT RUN | Partially verified | backend/API contract exists; full browser editing flow has not been exercised end-to-end |
| Onboarding completion/time | NOT RUN | Requires runtime testing | human pilot required |

## 5. Benchmark and source quality

| Gate | Status | Evidence class | Evidence / limitation |
|---|---|---|---|
| Public benchmark validator/report code | PASS | Verified | schema, size, leakage, privacy, dual-label, metric, and segment tests |
| Governed 320-judgment corpus | NOT RUN | Requires runtime testing | labels, adjudication, agreement, manifest, and frozen split are not fabricated |
| Final benchmark thresholds | NOT RUN | Requires runtime testing | requires governed corpus |
| Retained source-quality schema | PASS | Verified | bounded atomic privacy-safe history; requests/funnel/outcomes/failure categories per source |
| Source-quality API/CLI | PASS | Verified | local read-only API and `diagnose` report; no source run triggered |
| Inconclusive link handling | PASS | Verified | only 404/410 become confirmed dead; auth/block/rate-limit/server/TLS/network remain inconclusive |
| Per-source latency/cost | NOT RUN | Partially verified | explicitly reported as unavailable/null because adapters do not currently emit trustworthy per-source values |
| Retained real source report | NOT RUN | Requires runtime testing | no live source request was run during this work |

## 6. Privacy and lifecycle

| Gate | Status | Evidence class | Evidence / limitation |
|---|---|---|---|
| Accurate local/network wording | PASS | Verified | README/security docs distinguish local private state from configured source/provider network calls |
| Candidate artifacts absent from packages | PASS | Verified | wheel and sdist archive inspection |
| Backup/restore integrity | PASS | Verified | SQLite-consistent snapshot plus config/provider settings and secret round-trip; archive traversal/symlink/size checks and atomic restore |
| Reset jobs scope | PASS | Verified | clears job/catalog/run/funnel state; preserves profiles/onboarding/config; creates backup |
| Full local wipe | PASS | Verified | clears jobs, profiles, versions, provider settings/secrets, config, exports, cache/logs, pilot/source state; creates mandatory backup |
| Backup deletion choice | PASS | Verified | separate exact `DELETE BACKUPS` confirmation and CLI action |
| Ordered migration | PASS | Verified | production startup wiring, version 1 backup, representative legacy-row preservation, rollback, idempotence, and future-version rejection |
| Legacy data relocation | PASS | Verified | dry-run, verified copy, backup, atomic rename, no-overwrite behavior |
| Pilot metrics privacy | PASS | Verified | off by default, local, inspectable, allowlisted, redacted export, deletable, no uploader |
| Real participant pilot | NOT RUN | Requires runtime testing | opt-in human study required |

## 7. Security and accessibility

| Gate | Status | Evidence class | Evidence / limitation |
|---|---|---|---|
| Resume traversal/symlink/upload bounds | PASS | Verified | existing security tests |
| Restore traversal/symlink/corruption | PASS | Verified | lifecycle safety tests |
| Package/dependency audit | PASS | Verified | archive inspection, npm audit, pip-audit |
| Browser JavaScript/API smoke | PASS | Verified | no console or JS errors; local UI/API/assets returned successfully |
| Semantic landmarks and keyboard CTA | PASS | Partially verified | banner/main present; Tab visible 3px focus; Enter opens onboarding |
| Horizontal overflow at 1280px | PASS | Verified | browser inspection |
| 320px/200% reflow | NOT RUN | Requires runtime testing | dedicated viewport/zoom matrix required |
| Screen reader and full keyboard completion | NOT RUN | Requires runtime testing | manual assistive-technology evidence required |
| Contrast and serious/critical a11y scan | NOT RUN | Requires runtime testing | axe/contrast tooling not executed |
| Reduced-motion behavior | NOT RUN | Partially verified | CSS implementation exists; browser preference matrix not executed |

## 8. Cross-platform and pilot matrix

| Workflow | WSL/Linux | Ubuntu 22.04 | Ubuntu 24.04 | Windows | macOS 14/15 |
|---|---|---|---|---|---|
| Source tests/lint/build | PASS | PASS | PASS | PASS | PASS |
| Wheel install/help/health/assets | PASS | PASS | PASS | PASS | PASS |
| `run --no-open` lifecycle | PASS | PASS | PASS | PASS | PASS |
| Browser app-mode `desktop` | Partially verified | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| Automated onboarding/approval/discovery | PASS | PASS | PASS | PASS | PASS |
| Backup/restore/reset/wipe/migrate | PASS | PASS | PASS | PASS | PASS |
| Uninstall/data retention | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN |

GitHub Actions release-candidate run `29652907626` passed on Ubuntu 22.04/24.04, Windows 2022, and macOS 14/15. The browser-opening app-mode `desktop` path remains a separate manual/native evidence gate; CI validates the non-opening server lifecycle.

Pilot gates remain `NOT RUN`: install success, onboarding completion/time, first relevant result, top-5/top-10 relevance, repeat use, explanation trust, privacy understanding, prohibited-export count, and unsafe Ready count.

## 9. Ship decision

The working tree becomes eligible for a public ship decision only after:

1. the exact diff is reviewed and frozen in a candidate commit;
2. the governed benchmark corpus is labeled/adjudicated and all non-waivable thresholds pass;
3. a real retained source-quality run and useful-listing review pass;
4. the opt-in human pilot passes its safety, usefulness, privacy, and completion gates;
5. accessibility automation and manual keyboard/screen-reader/reflow evidence pass;
6. maintainer review explicitly approves the artifacts and publication.

**Current result: NO-SHIP for public Version 1 release.** The implementation and automated cross-platform candidate are substantially verified, but human benchmark, live-source usefulness, pilot, manual desktop, and accessibility evidence gates remain intentionally open.
