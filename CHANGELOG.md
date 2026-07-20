# Changelog

All notable changes to Opportune are documented here.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic versioning.

## [Unreleased]

## [0.1.1] - 2026-07-20

### Added

- One-command browser launch through `opportune run` and `opportune desktop`, with bounded readiness and loopback-only defaults.
- Immutable approved-profile versions, draft edits, transactional approval, and fail-closed source boundaries.
- Versioned discovery-funnel diagnostics across persistence, API, CLI, and dashboard empty states.
- Ordered, backup-preserving SQLite migrations and platform-aware writable data paths.
- Public benchmark validation/reporting, opt-in local pilot metrics, and retained privacy-safe source-quality reports.
- Native release-candidate CI, installed-wheel smoke testing, and wheel/sdist privacy enforcement.
- Structured GitHub Issue forms, Pull Request template, CI, Dependabot, support policy, and maintainer guide.
- Public dashboard and onboarding screenshots.
- Future email-evidence/outreach schema and safety design.
- Cached GitHub Release checks through the dashboard and `opportune update check`, with an explicit review link instead of silent installation.

### Changed

- Compact U.S. location aliases now normalize consistently across onboarding, acquisition queries, and guardrails.
- Link checks reject private and unsafe redirect destinations; only HTTP 404/410 are classified as confirmed dead.
- Local lifecycle controls distinguish job reset, full wipe, restore, and separately confirmed backup deletion.
- Dashboard behavior is responsive, keyboard-visible, reduced-motion aware, and exposes actionable no-result states.
- Dashboard and onboarding copy is concise and non-technical.
- Branding now uses the Opportune forest, mint, and warm-cream palette.
- Approved onboarding profiles are the only supported search-activation path.

### Fixed

- Onboarding work focus accepts up to three ordered choices while preserving the first choice as the backward-compatible primary focus.
- Location entry preserves spaces and commas while typing instead of destructively normalizing the visible text after every keystroke.

### Deferred

- Email-derived application evidence and outreach remain outside v0.1 until the privacy, consent, and approval model in `docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md` is implemented and verified.

## [0.1.0] - 2026-07-17

Initial public release candidate:

- local guided onboarding with profile approval;
- local/BYO model providers;
- public job-source adapters and scheduler;
- deterministic matching and safety gates;
- React dashboard, review queue, and local data controls;
- package, CLI, tests, and release workflow.
