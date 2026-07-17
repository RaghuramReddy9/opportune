# Roadmap

## v0.1 — local job search foundation

Implemented:

- [x] Guided resume onboarding with an explicit approval gate.
- [x] PDF, DOCX, TXT, Markdown, and pasted-text ingestion.
- [x] Private local analysis and bring-your-own OpenAI, OpenRouter, Ollama, or compatible model.
- [x] Five required search decisions and reviewable final plan.
- [x] Multiple local profiles and profile switching.
- [x] Incremental ATS catalog with first/last seen and active/missing/closed state.
- [x] Company career pages, curated lists, and optional API adapters.
- [x] Broad role-and-location pool before strict ranking.
- [x] Transparent match, eligibility, freshness, and safety evidence.
- [x] Labeled ranking benchmark with unsafe-recommendation gate.
- [x] React dashboard with discovery filters and review drawer.
- [x] Local scheduler with separate direct-source and board-source intervals.
- [x] SQLite storage, JSON export, verified backup, and confirmed wipe.
- [x] Short `opp` CLI with JSON output for scripts and agents.
- [x] Demo jobs, doctor, audit, quality, and local job-management commands.
- [x] Legacy Gmail, evidence, outreach, static-dashboard, and old cron paths removed.
- [x] MIT license and generic public examples.

Release work:

- [x] Backend tests, Ruff, ranking quality gate, frontend lint/build, dependency audit, and installed-wheel smoke test in the development tree.
- [x] GitHub CI, Issue forms, PR template, security policy, and contributor docs.
- [ ] Clean-history candidate passes the complete release checklist.
- [ ] Maintainer reviews the exact candidate tree and commit.
- [ ] Candidate is pushed to the private `opportune` repository.
- [ ] Maintainer explicitly approves public visibility and `v0.1.0` release.

## Planned v0.2 — application evidence and reviewed follow-up

Design: [`docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md`](docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md)

Planned scope:

- [ ] Provider-neutral read-only email connection, starting with Gmail OAuth.
- [ ] Redacted, idempotent message observations.
- [ ] Suggested links between messages and saved jobs.
- [ ] Append-only application event ledger.
- [ ] User verification before lifecycle changes.
- [ ] Follow-up eligibility from verified events.
- [ ] Draft-only outreach with a separate approval and send action.
- [ ] Account revocation, selective deletion, and complete feature wipe.
- [ ] Labeled false-update, duplicate-sync, duplicate-send, and privacy gates.

Not planned for the first evidence release:

- autonomous campaigns;
- cold-email address discovery;
- automatic replies;
- sending without a final approval screen.

## Later possibilities

- Additional well-governed source plugins.
- Docker/Podman one-command launch.
- Richer source-health and API-usage views.
- Optional resume tailoring that never submits automatically.
- Accessibility and keyboard-navigation improvements.
- Hosted documentation.

## Ongoing non-goals

- Automatic application submission.
- Hidden or default-on external writes.
- Bypassing authentication, CAPTCHAs, robots rules, or source restrictions.
- Storing user data outside the local machine by default.
- Multi-user hosted SaaS in the v0.x line.
