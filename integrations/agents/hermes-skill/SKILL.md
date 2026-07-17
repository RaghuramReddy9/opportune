---
name: opportune
description: Operate a local-first Opportune checkout through its JSON CLI.
---

# Opportune Skill

Use when working inside a cloned `opportune` repo.

## Inspect

```bash
uv run python jobhunt.py tools --json
uv run python jobhunt.py doctor --json
uv run python jobhunt.py audit --json
```

## First run

```bash
uv sync
uv run python jobhunt.py quickstart --json
uv run python jobhunt.py dashboard
```

## Jobs

```bash
uv run python jobhunt.py jobs list --json --limit 20
uv run python jobhunt.py jobs list --json --action-tag apply_now
uv run python jobhunt.py jobs update '<job_uid>' --status watch --note 'review later' --json
```

## Rules

- Keep all job/resume data local.
- Never commit `.env`, `config.yaml`, tracker DBs, resume uploads, exports, reports, backups, `.hermes/`, or `.memory/`.
- Scrape is dry-run unless `--live` is passed.
- Do not add mandatory LLM/API dependencies.
- Verify backend changes with `uv run python -m pytest tests/ -q`.
