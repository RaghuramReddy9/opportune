# Agent Instructions

This repo is local-first and privacy-aware. Keep every change small, tested, and easy to review.

Before coding:
1. Read the real file/function you will touch.
2. Check whether the code already exists.
3. Prefer deletion, reuse, or config over new abstractions.
4. Keep the diff as small as possible.
5. Do not add dependencies unless the existing stack cannot solve it.

Agent operation:
1. Discover commands with `uv run python jobhunt.py tools --json`.
2. Check setup with `uv run python jobhunt.py doctor --json`.
3. Prefer JSON output for inspection and local automation.
4. Treat `scrape` as dry-run unless `--live` is explicitly requested.
5. Treat `privacy wipe` as destructive-local and ask first.

Before finishing:
1. Run the smallest meaningful verification.
2. For backend changes: `uv run python -m pytest tests/ -q`.
3. For frontend changes: `cd frontend && npm run build`.
4. Never commit `.env`, `config.yaml`, `tracker/*.db`, resume uploads, reports, exports, backups, `.release/`, `.hermes/`, or `.memory/`.

Public-release rule:
Use a feature branch and protected pull request for the canonical public repository. Do not tag or publish a release until the evidence gates in `PUBLIC_RELEASE.md` and `RELEASE_SCORECARD.md` pass and the maintainer explicitly approves it.
