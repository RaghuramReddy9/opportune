# Maintaining Opportune

This guide describes how to keep the public project healthy after v0.1.

## Repository policy

- `RaghuramReddy9/opportune` is the public product repository.
- The historical development repository stays private.
- After the clean candidate is published and verified, archive the old repository instead of deleting it.
- Delete the historical repository only after a separate review confirms that a complete backup exists and no rollback, attribution, or forensic value remains.
- Never merge private history into the public repository.

## Protected `main`

Configure branch protection to require:

- Pull Requests for changes;
- CI checks for Python 3.10, Python 3.12, and frontend;
- resolved review conversations;
- no force pushes;
- no branch deletion.

Maintainers may merge their own small fixes only after the same CI checks pass.

## Issue triage

Review new Issues at least weekly when the project is active.

1. Remove or redact exposed secrets and personal data immediately.
2. Route security reports to private vulnerability reporting.
3. Confirm the report is in scope and reproducible.
4. Apply labels.
5. Ask for the smallest missing evidence.
6. Close duplicates with a link to the canonical Issue.
7. Keep roadmap decisions in Issues rather than private chat alone.

Suggested labels:

- `bug`, `enhancement`, `documentation`;
- `source-request`, `privacy`, `security`;
- `frontend`, `python`, `dependencies`, `ci`;
- `needs-triage`, `needs-reproduction`;
- `good first issue`, `help wanted`;
- `blocked`, `wontfix`, `duplicate`.

## Pull Request review

Review for:

- one clear user problem;
- minimal scope;
- deterministic tests;
- privacy and network-boundary changes;
- source-access legitimacy;
- natural user-facing copy;
- updated docs;
- absence of secrets and personal data.

Do not accept a PR that weakens a safety gate or test merely to pass CI.

Prefer squash merge for contributor PRs so public history stays focused. Use an informative imperative commit subject.

## Dependency maintenance

Dependabot checks Python, npm, and GitHub Actions weekly.

For each dependency PR:

1. read release and security notes;
2. verify lockfile changes are limited;
3. run the full CI suite;
4. perform an installed-wheel smoke test for runtime dependencies;
5. merge only when behavior and supported Python versions remain intact.

## Release process

Opportune follows semantic versioning while in v0.x:

- patch: compatible bug, documentation, or security fix;
- minor: new supported behavior or material schema/API change;
- major: reserved for a stable post-v0 compatibility commitment.

For each release:

1. freeze features;
2. update `CHANGELOG.md`, version metadata, and roadmap;
3. run all checks in `PUBLIC_RELEASE.md`;
4. inspect the exact diff and tracked file list;
5. build and install the wheel in a clean environment;
6. smoke-test onboarding and an existing profile;
7. scan for secrets, personal data, and vulnerable dependencies;
8. create a signed or annotated `vX.Y.Z` tag;
9. publish GitHub release notes;
10. monitor new Issues and failed installs.

PyPI publication is a separate approval and should happen only after the GitHub release artifact is verified.

## Database changes

Schema changes must be additive where possible and tested against:

- a clean database;
- the previous released schema;
- multiple profiles;
- backup/export behavior;
- wipe behavior.

Never add email evidence or outreach tables ad hoc. Follow `docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md` and its release gates.

## Documentation maintenance

Behavior changes must update the nearest public source of truth:

- `README.md` for user setup and scope;
- `ARCHITECTURE.md` for boundaries and data flow;
- `ROADMAP.md` for planned work;
- `CONTRIBUTING.md` for contributor procedure;
- `SECURITY.md` for trust boundaries;
- `PUBLIC_RELEASE.md` for release gates.

Screenshots should be recaptured when the main layout or onboarding changes. Use synthetic or public listing data and verify that no private information is visible.
