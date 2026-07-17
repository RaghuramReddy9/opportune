# Contributing to Opportune

Thank you for helping improve Opportune. Bug reports, source requests, documentation fixes, and focused pull requests are welcome.

## Start with the right GitHub item

- Use a **Bug report** when existing behavior is broken.
- Use a **Feature request** to propose a product change.
- Use a **Source request** for a new job source or adapter.
- Use a **security report**, not a public Issue, for vulnerabilities.

For a large change, open an Issue before implementation so scope, privacy, and source-access constraints can be agreed first.

## Fork-and-pull workflow

1. Fork `RaghuramReddy9/opportune`.
2. Clone your fork.
3. Create a focused branch.
4. Make the smallest complete change.
5. Add or update tests.
6. Run all relevant checks.
7. Push to your fork.
8. Open a Pull Request against `main`.

```bash
git clone https://github.com/<your-user>/opportune.git
cd opportune
git switch -c fix/short-description

uv sync
cd frontend && npm ci && cd ..
```

## Development checks

Backend or cross-cutting changes:

```bash
uv run ruff check .
uv run pytest -q
uv run opp quality --json
uv build
```

Frontend changes:

```bash
cd frontend
npm run lint
npm run build
```

A Pull Request should not weaken a test, safety gate, privacy check, or accessibility behavior merely to make the change pass.

## Project boundaries

### Local-first

Opportune stores its supported application state in local SQLite. External sources are inputs, not hidden storage sinks.

Do not introduce a network write, hosted dependency, analytics service, or telemetry without an explicit design discussion and a default-off user control.

### Approved profile flow

Resume analysis creates a draft. Search activation must remain behind the five-question review and approval flow.

Do not reintroduce a route, CLI command, or Settings form that silently creates or activates a profile.

### Secrets and user data

Never commit:

- `.env` or API keys;
- `config.yaml`;
- SQLite databases;
- uploaded resumes or onboarding sessions;
- exports, backups, logs, or scheduler state;
- personal job-search records.

Use generic fixtures and `example.com` URLs in tests.

### Source access

A new source adapter must:

- use a documented public endpoint or access method permitted by current terms;
- be disabled unless explicitly configured;
- identify whether it is free or requires a paid/keyed account;
- obey rate limits, robots directives, and blocking;
- avoid authentication bypass, CAPTCHAs, or evasion;
- normalize results into the existing job schema;
- include deterministic tests with no live network dependency;
- report source health and errors without leaking keys.

If a source requires Apify, document installation through `opportune[apify]`.

## Where changes belong

| Change | Primary path |
|---|---|
| Job-source adapter | `adapters/` plus `core/source_registry.py` / config example |
| Discovery behavior | `pipeline/` |
| Ranking or safety | `ranking/` plus labeled fixtures |
| Database or profiles | `dashboard/db.py` |
| Local API | `dashapi/server.py` |
| Dashboard UI | `frontend/src/App.tsx` and `frontend/src/index.css` |
| Onboarding UI | `frontend/src/onboarding/` |
| Resume providers/parsing | `onboarding/` |
| CLI | `jobhunt.py` |
| Public local operations | `public_ops.py` |

Read `ARCHITECTURE.md` before changing boundaries between these layers.

## Code expectations

- Prefer existing abstractions over new parallel paths.
- Delete replaced code instead of leaving disabled implementations.
- Keep functions and modules focused.
- Validate external data at its boundary.
- Make errors actionable without exposing secrets.
- Preserve deterministic tests; mock external networks.
- Keep user-facing copy concise, natural, and non-technical unless the screen is explicitly diagnostic.
- Update README, architecture, roadmap, and examples when behavior changes.

## Pull Request description

Explain:

- the user problem;
- the smallest implemented solution;
- affected privacy or network boundaries;
- tests and manual checks run;
- screenshots for visible UI changes;
- any follow-up intentionally left out.

Link the Issue with `Fixes #<number>` when appropriate.

## Review and merge

Maintainers may request smaller scope, stronger tests, source-access evidence, wording changes, or removal of unnecessary code.

A PR is ready to merge when:

- required CI checks pass;
- review comments are resolved;
- docs match behavior;
- no secrets or personal data are present;
- the change is understandable as one focused unit.

See `CODE_OF_CONDUCT.md` for community expectations and `SECURITY.md` for private vulnerability reporting.
