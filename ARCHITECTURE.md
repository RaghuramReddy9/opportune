# Opportune architecture

## Purpose

Opportune maintains a local pool of job listings, ranks them against an approved search profile, and keeps every recommendation reviewable.

v0.1 is a local, single-user application. It is not a hosted multi-user service.

## Runtime flow

```text
Resume + five user decisions
    ↓
Draft onboarding session
    ↓ explicit approval
Active search profile in SQLite
    ↓
Enabled source adapters
    ↓
Incremental source catalog
    ↓
Role + location discovery pool
    ↓
Ranking, eligibility, and safety gates
    ↓
SQLite dashboard model
    ↓
FastAPI local API + React dashboard
```

## Configuration precedence

Opportune separates a user's approved search from runtime configuration.

### Active profile: search intent

The active profile in `tracker/dashboard.db` contains the onboarding decisions that control discovery and ranking:

- roles and work focus;
- target levels;
- locations and work modes;
- work authorization;
- skills and resume evidence;
- exclusions and listing age.

A profile is inactive until the user approves the final onboarding plan.

### `config.yaml`: runtime and sources

The local YAML file controls:

- enabled sources and their free/paid classification;
- scheduler intervals;
- SQLite location;
- dashboard host and port;
- fallback defaults used before an approved profile exists.

When a profile is active, its approved search fields override profile defaults from YAML. Source and runtime settings continue to come from YAML.

Secrets are environment variables or onboarding provider-key files. They are not stored in `config.yaml`.

## Main modules

| Path | Responsibility |
|---|---|
| `onboarding/` | Provider choice, resume reading, sanitization, five-question draft, approval |
| `adapters/` | Individual external job-source integrations |
| `pipeline/query_strategy.py` | Builds source queries from the active profile |
| `pipeline/scrape.py` | Runs source work, normalizes results, and coordinates ranking/storage |
| `pipeline/discovery_pool.py` | Materializes the broad role-and-location pool |
| `pipeline/scheduler.py` | Durable direct-source and board-source scheduling |
| `ranking/` | Scoring, targeting, eligibility, guardrails, and quality benchmark |
| `dashboard/db.py` | SQLite schema, profile state, catalog state, jobs, and dashboard projection |
| `dashapi/server.py` | Local FastAPI API and React asset serving |
| `frontend/src/` | React dashboard and onboarding interface |
| `public_ops.py` | Local config, demo, export, backup, and wipe operations |
| `jobhunt.py` | `opp` / `opportune` CLI |

## Onboarding state model

Onboarding follows an explicit state transition:

```text
welcome
  → provider selected
  → resume analyzed
  → five questions answered
  → plan ready for review
  → user approved
  → active profile created
```

Discovery endpoints call `_require_approved_profile()` and return HTTP 409 when no active profile exists.

Resume ingestion supports PDF, DOCX, TXT, Markdown, and pasted text. File parsing and local analysis stay on the machine. A remote provider is called only when the user chooses one.

Provider keys:

- are stored separately from provider metadata;
- use restrictive local file permissions;
- are not returned by API responses;
- are excluded from Git and release candidates.

## Discovery model

### Source enablement

Each source has a stable name, label, enabled flag, mode, and optional environment-key name. A source missing from `config.yaml` is disabled. An environment key never enables a source by itself.

### Catalog before ranking

Direct ATS adapters download source snapshots. The catalog records:

- stable source identity;
- first and last seen timestamps;
- content hash and change time;
- listing state: `active`, `missing`, or `closed`;
- confirmed or unknown publication date.

`pipeline/discovery_pool.py` selects role-and-location matches from the catalog before strict resume scoring. This keeps source truth separate from recommendation decisions.

### Ranking and eligibility

Core layers:

- `ranking/score.py` — resume/profile match score;
- `ranking/targeting.py` — role family and level classification;
- `ranking/eligibility.py` — ready, review, or excluded decision;
- `ranking/guardrails.py` — location, freshness, source, and risk checks;
- `ranking/benchmark.py` — labeled-fixture release gate;
- `core/skill_matcher.py` — skill coverage and missing-skill evidence.

A listing found without a reliable posted date is `Newly Discovered`. It may be reviewed but cannot enter the strongest recommendation bucket solely because Opportune just found it.

## SQLite ownership

`tracker/dashboard.db` is the supported application database. It contains:

- profiles and the active-profile pointer;
- onboarding sessions;
- job catalog/listing state;
- ranked jobs and application status;
- scrape runs and enrichment queue.

v0.1 does not maintain separate evidence, jobs, or application CSV databases.

## Local API

Important endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Local runtime, catalog, source, and scheduler health |
| `GET /api/dashboard` | Active-profile dashboard model |
| `GET/POST /api/config` | Read or update runtime/source config |
| `GET /api/onboarding` | Resume onboarding state without resume text or keys |
| `POST /api/onboarding/analyze` | Analyze pasted resume text |
| `POST /api/onboarding/upload` | Parse and analyze a resume file |
| `POST /api/onboarding/{id}/answers` | Store five onboarding answers |
| `POST /api/onboarding/{id}/approve` | Create and activate the approved profile |
| `GET /api/profiles` | List local profiles |
| `POST /api/profiles/{id}/activate` | Switch active profile |
| `POST /api/scrape` | Dry-run or save discovery results; approved profile required |
| `POST /api/smart-scrape` | Bounded multi-window discovery |
| `GET/POST /api/jobs...` | Local job listing, note, and status operations |
| `POST /api/privacy/export` | Export job rows to JSON |
| `POST /api/privacy/backup` | Snapshot SQLite and config into a verified ZIP |
| `POST /api/privacy/wipe` | Back up, then delete local job rows after `WIPE` confirmation |

The removed `/api/profile/resume` bypass is intentionally not part of v0.1. Profile activation must go through onboarding approval.

## Browser security boundary

The server:

- binds to `127.0.0.1` by default;
- uses trusted-host middleware;
- rejects cross-origin state-changing requests;
- redacts credential-like values in health output;
- never returns provider keys;
- serves one built React bundle from `frontend/dist`.

Binding to a non-loopback interface changes the security model and is not a supported default.

## Data ownership

Tracked files contain source code, public fixtures, and generic examples. User-owned state is ignored:

- `.env`
- `config.yaml`
- `tracker/*.db`
- `tracker/onboarding/*`
- `tracker/backups/*`
- `exports/*`

The clean public repository must not include a development database, resume, provider settings, release runtime, or old private Git history.

## Deferred architecture

Email evidence and outreach are absent from v0.1. Their planned provider-neutral, append-only, approval-gated design is in [`docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md`](docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md).
