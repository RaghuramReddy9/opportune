# Public release checklist

The private development repository must not be made public directly. Its older history may contain personal or obsolete project data even when the current working tree is clean.

## Release model

1. Finish and verify the development tree.
2. Export an allowlisted clean tree into `.release/opportune`.
3. Initialize a new Git repository with one release-candidate commit.
4. Run every gate again inside that clean repository.
5. Show the exact tree, commit, scans, and known limits to the maintainer.
6. Push only after maintainer approval to push.
7. Keep the new GitHub repository private until explicit public-release approval.
8. Tag `v0.1.0` only from the verified public candidate.

## Candidate must contain

- Source modules used by v0.1.
- React source and production assets.
- Tests and ranking fixtures.
- Generic config/profile/resume examples.
- README, architecture, roadmap, contributing, security, support, code of conduct, and license.
- GitHub CI, Issue forms, and PR template.

## Candidate must not contain

- `.git/` from the development repository.
- `.env`, `config.yaml`, API keys, or provider-key files.
- SQLite databases or scheduler state.
- Uploaded resumes or onboarding sessions.
- Reports, exports, backups, logs, caches, build directories, or virtual environments.
- `.hermes/`, `.memory/`, `.kilo/`, or `.release/`.
- Gmail/evidence/outreach implementation from the private legacy history.
- Personal names, paths, contact details, or job-search records outside intentional project authorship.

## Automated gates

Run from the clean candidate:

```bash
uv sync --frozen
uv run ruff check .
uv run pytest -q
uv run opp quality --json

cd frontend
npm ci
npm run lint
npm run build
cd ..

uv build
uv run opp audit --json
```

Expected minimums:

- all Python tests pass;
- Ruff reports no errors;
- frontend lint reports no warnings or errors;
- TypeScript and Vite production build succeed;
- ranking quality reports `ok: true` and zero unsafe false-Apply decisions;
- source audit reports no release blocker;
- source distribution and wheel build successfully.

## Installed-artifact smoke test

Do not validate only from the source tree.

1. Create a temporary virtual environment outside the candidate.
2. Install the built wheel.
3. Run `opp --help` and confirm `start`, `doctor`, `quality`, and `privacy` are present.
4. Run `opp doctor --json` in an empty temporary working directory.
5. Start the installed dashboard on a temporary port.
6. Confirm:
   - `/` serves the React shell;
   - `/api/health` returns `service: opportune`;
   - `/api/onboarding` returns a safe resumable state;
   - `/api/profile/resume` is absent from OpenAPI;
   - static JS/CSS assets return 200.

## First-run acceptance

Use an empty temporary SQLite database:

1. `opp start` opens onboarding instead of an empty dashboard.
2. The provider screen distinguishes local and remote processing.
3. PDF, DOCX, TXT, Markdown, and pasted text are handled as documented.
4. Resume analysis creates a draft with exactly five required questions.
5. Discovery returns HTTP 409 before profile approval.
6. The review plan shows roles, levels, locations, work modes, work authorization, skills, and exclusions.
7. Approval creates and activates one profile.
8. The dashboard opens without losing onboarding state.
9. Settings points back to the reviewed onboarding flow; it has no bypassing resume form.
10. Existing installations with an active profile open the dashboard directly.
11. Generic profile names do not produce unnatural greetings.

## Privacy and secret scans

The release script or equivalent checks must fail on:

- tracked ignored-runtime paths;
- common API-key/private-key formats;
- provider key files;
- SQLite, ZIP, or uploaded-resume artifacts;
- private names and absolute development paths;
- legacy Gmail implementation paths.

After building the wheel, inspect both archives and repeat the same checks against archive member names and text content.

## Dependency and package checks

- Python dependency vulnerability scan passes.
- Frontend production dependency audit passes.
- Direct dependencies match direct imports.
- Optional Apify support is exposed through `opportune[apify]`.
- Wheel metadata reports package/version `opportune 0.1.0`, MIT license, README, and repository URLs.

## GitHub readiness

Before public visibility:

- CI passes on the candidate commit.
- Issues are enabled.
- Private vulnerability reporting is enabled.
- Bug, feature, and source-request forms are present.
- PR template and code of conduct are visible.
- Repository description and topics describe Opportune v0.1 only.
- Default branch protection requires CI before merge.

## Maintainer approval packet

Show the maintainer:

- private repository URL;
- candidate commit hash;
- complete top-level tree;
- file count and language summary;
- final test, lint, build, quality, package, vulnerability, and secret-scan results;
- known limitations;
- exact command that would push or change visibility.

No push, visibility change, tag, release, or deletion occurs before the corresponding approval.
