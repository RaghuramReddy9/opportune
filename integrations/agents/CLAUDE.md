# Claude Code Notes

This project is a local-first job search dashboard and CLI.

Start by running:

```bash
uv run python jobhunt.py tools --json
uv run python jobhunt.py doctor --json
```

Important:

- The app does not require LLM inference for core behavior.
- Do not introduce required cloud services or hosted storage.
- User secrets belong in `.env`; local config belongs in ignored `config.yaml`.
- Job/resume data stays in ignored local tracker paths.
- Use dry-run first: `uv run python jobhunt.py scrape --json`.
- Use `--live` only when the user wants local SQLite writes.
- Scope discovery with `--source-group direct` or `--source-group board`.
- The broad pool is role+location based; do not reintroduce resume, freshness,
  experience, or work-mode rejection before local persistence.
- Inspect `schedule status --json` before running scheduled work.
- Use `jobs rebuild-pool --json` for an offline catalog-to-pool rebuild.
- Run `quality --json` after ranking or guardrail changes; all release gates must pass.

Common checks:

```bash
uv run python -m pytest tests/ -q
uv run python jobhunt.py quality --json
uv run python jobhunt.py schedule status --json
cd frontend && npm run build
```
