# Agent Notes for Opportune

Use the JSON CLI first:

```bash
uv run python jobhunt.py tools --json
uv run python jobhunt.py doctor --json
uv run python jobhunt.py schedule status --json
uv run python jobhunt.py quality --json
```

Do not guess DB paths or config shape. Read them through the CLI.

Safe first workflow:

```bash
uv sync
uv run python jobhunt.py quickstart --json
uv run python jobhunt.py doctor --json
uv run python jobhunt.py dashboard
```

Development rules:

- Keep changes small and easy to review.
- Reuse existing helpers before adding new ones.
- Keep user data local.
- Do not add mandatory LLM/API dependencies.
- Add tests for behavior changes.
- Keep source acquisition separate from recommendation: configured role title
  plus verified location populate the broad local pool; resume, freshness,
  experience, and work-mode filters narrow it afterward.
- Use `scrape --source-group direct|board` when validating one acquisition tier.
- Use `jobs rebuild-pool --json` to re-materialize the current catalog without network access.
- Never use `schedule run --force` without explicit user intent; it performs local writes and network discovery.
- Verify with `uv run python -m pytest tests/ -q` and `cd frontend && npm run build` for UI work.
