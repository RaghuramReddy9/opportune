# Agent Integration

Opportune is designed to be operated by shell-capable coding agents without special plugins.

The stable interface is the JSON CLI:

```bash
uv run opp tools --json
uv run opp doc --json
uv run opp jobs ls --json --limit 20
```

## Rules for agents

- Treat this as a local-first tool. Do not send resume/job data to external services unless the user explicitly enables that feature.
- Prefer JSON commands for inspection.
- Use `scrape` without `--live` first; it is dry-run by default.
- Use `--source-group direct` for all configured ATS snapshots or
  `--source-group board` for configured board/API discovery.
- `schedule run --once` writes due discovery results locally; inspect
  `schedule status` first unless the user explicitly asks to force a run.
- Run `quality --json` before changing ranking thresholds or claiming release readiness.
- `jobs rebuild-pool` materializes role+location matches from the existing
  local catalog without making network requests.
- `jobs update` writes only to local SQLite and never submits applications.
- Never commit `.env`, `config.yaml`, tracker databases, resume uploads, exports, backups, reports, `.hermes/`, or `.memory/`.
- Run `uv run python -m pytest tests/ -q` after backend changes.
- Run `cd frontend && npm run build` after UI changes.

## Useful commands

```bash
# discover available tool-like commands
uv run opp tools --json

# check setup health
uv run opp doc --json

# create config and seed demo jobs if empty
uv run opp q --json

# list best local jobs
uv run opp jobs ls --json --action-tag apply_now --limit 10

# mark a job locally
uv run opp jobs update '<job_uid>' --status watch --note 'review later' --json

# run Smart Scrape dry-run
uv run opp smart --json

# run Smart Scrape and write dashboard cards locally
uv run opp smart --live --json

# inspect or run the durable local scheduler
uv run opp schedule status --json
uv run opp schedule run --once --json

# run all direct ATS feeds in dry-run mode
uv run opp scrape --source-group direct --json

# rebuild the broad local role+location pool without scraping
uv run opp jobs rebuild-pool --json

# verify labeled ranking safety gates
uv run opp quality --json
```

## Safety classes

`tools --json` labels each command as:

- `read-only`
- `local-write`
- `read-only by default; local-write with --live`
- `destructive-local`

Agents should ask before running `destructive-local` commands.
