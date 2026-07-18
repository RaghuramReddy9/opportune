#!/usr/bin/env python3
"""jobhunt — command-line entrypoint for local-first job-hunt automation.

Agent-friendly: every read command accepts --json for machine-readable output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config as cfg  # noqa: E402


VALID_STATUSES = {"discovered", "watch", "applied", "confirmed", "interview", "assessment", "offer", "rejected", "closed"}


def _dump(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def _load_yaml_file(p: Path):
    import yaml
    return yaml.safe_load(p.read_text()) if p.exists() else {}


def _check(code: str, status: str, message: str, **extra: Any) -> dict[str, Any]:
    item = {"code": code, "status": status, "message": message}
    item.update(extra)
    return item


def run_doctor() -> dict[str, Any]:
    """Return local health checks for humans and agents."""
    from dashboard import db as dashboard_db

    checks: list[dict[str, Any]] = []
    if cfg.CONFIG_PATH.exists():
        config_data = _load_yaml_file(cfg.CONFIG_PATH)
        checks.append(_check("config_exists", "ok", f"config found at {cfg.CONFIG_PATH}"))
    else:
        config_data = _load_yaml_file(cfg.CONFIG_EXAMPLE_PATH)
        checks.append(_check("config_missing", "warning", f"config.yaml missing; using template {cfg.CONFIG_EXAMPLE_PATH}"))

    try:
        dashboard_db.init_db()
        db_path = dashboard_db.get_db_path()
        with dashboard_db.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        checks.append(_check("sqlite_writable", "ok", f"SQLite writable at {db_path}", path=str(db_path), total_jobs=total))
    except Exception as exc:  # pragma: no cover - defensive path
        checks.append(_check("sqlite_writable", "error", f"SQLite check failed: {exc}"))
        total = 0

    sources = config_data.get("sources", []) or []
    for source in sources:
        if not source.get("enabled"):
            checks.append(_check("source_disabled", "info", f"{source.get('name')} disabled", source=source.get("name")))
            continue
        env_key = source.get("api_key_env")
        if source.get("mode") == "paid" and env_key and not os.getenv(env_key):
            checks.append(_check("missing_api_key", "warning", f"{source.get('name')} enabled but {env_key} is not set", source=source.get("name"), env_key=env_key))
        else:
            checks.append(_check("source_ready", "ok", f"{source.get('name')} ready", source=source.get("name")))

    active_profile = dashboard_db.get_active_profile()
    if active_profile:
        checks.append(
            _check(
                "profile_active",
                "ok",
                "approved search profile is active",
                profile_id=active_profile["profile_id"],
                name=active_profile.get("name", ""),
            )
        )
    else:
        checks.append(
            _check(
                "profile_missing",
                "warning",
                "no approved search profile; start the dashboard and complete onboarding",
            )
        )

    dashboard = config_data.get("dashboard", {}) or {}
    checks.append(_check("dashboard_config", "ok", "dashboard configured", host=dashboard.get("host", cfg.DASHBOARD_HOST), port=dashboard.get("port", cfg.DASHBOARD_PORT)))
    errors = [c for c in checks if c["status"] == "error"]
    warnings = [c for c in checks if c["status"] == "warning"]
    return {"ok": not errors, "summary": {"errors": len(errors), "warnings": len(warnings), "total_jobs": total}, "checks": checks}


def run_quickstart(*, seed_demo: bool = True) -> dict[str, Any]:
    """Create local config if needed and optionally seed sample jobs."""
    from dashboard import db as dashboard_db
    from public_ops import seed_demo_data

    created_config = False
    if not cfg.CONFIG_PATH.exists():
        cfg.CONFIG_PATH.write_text(cfg.CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        created_config = True
    dashboard_db.init_db()
    with dashboard_db.connect() as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
    seeded = None
    if seed_demo and before == 0:
        seeded = seed_demo_data(clear_first=False)
    with dashboard_db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
    return {
        "ok": True,
        "created_config": created_config,
        "seeded_demo": bool(seeded),
        "total_jobs": total,
        "dashboard_url": f"http://{cfg.DASHBOARD_HOST}:{cfg.DASHBOARD_PORT}",
        "next_steps": [
            "uv run opp start",
            "open the dashboard URL",
            "complete the guided resume onboarding",
        ],
    }


def run_jobs_list(*, status: str | None = None, action_tag: str | None = None, query: str = "", limit: int = 50) -> dict[str, Any]:
    from dashboard import db as dashboard_db

    dashboard_db.init_db()
    with dashboard_db.connect() as conn:
        jobs = dashboard_db.list_jobs(conn, status=status, action_tag=action_tag, limit=max(1, min(limit, 500)))
    if query:
        q = query.lower()
        jobs = [j for j in jobs if any(q in str(j.get(k, "")).lower() for k in ("company", "title", "location", "source", "why_matches"))]
    return {"ok": True, "count": len(jobs), "jobs": jobs}


def run_jobs_update(job_uid: str, status: str, note: str | None = None) -> dict[str, Any]:
    from dashboard import db as dashboard_db

    if status not in VALID_STATUSES:
        return {"ok": False, "error": f"invalid status: {status}", "valid_statuses": sorted(VALID_STATUSES)}
    dashboard_db.init_db()
    with dashboard_db.connect() as conn:
        updated = dashboard_db.set_job_status(conn, job_uid, status, note=note)
        job = dashboard_db.get_job(conn, job_uid) if updated else None
    return {"ok": updated, "job": job, "error": None if updated else "job not found"}


def run_smart_scrape(*, live: bool = False, min_high: int = 3, max_selected: int = 15) -> dict[str, Any]:
    from dashboard import db as dashboard_db
    from pipeline.smart_scrape import smart_scrape

    result = smart_scrape(live=live, min_high=min_high, max_selected=max_selected)
    if live:
        dashboard_db.init_db()
        with dashboard_db.connect() as conn:
            for job in result.get("dashboard_jobs", []):
                dashboard_db.upsert_scraped_job(conn, job, check_links=False)
            result["dashboard"] = dashboard_db.get_dashboard_model(conn)
    return result


def run_scrape(
    *,
    live: bool = False,
    window: str = "morning",
    source_group: str = "window",
    max_selected: int = 15,
) -> dict[str, Any]:
    """Run one scrape and sync its review cards when live."""
    from dashboard import db as dashboard_db
    from pipeline.scrape import scrape_all

    result = scrape_all(
        max_selected=max_selected,
        dry_run=not live,
        run_window=window,
        source_group=source_group,
    )
    if live:
        dashboard_db.init_db()
        with dashboard_db.connect() as conn:
            for job in result.get("dashboard_jobs", []):
                dashboard_db.upsert_scraped_job(conn, job, check_links=False)
            result["dashboard"] = dashboard_db.get_dashboard_model(conn)
    return result


def tools_manifest() -> dict[str, Any]:
    """Machine-readable command manifest for coding agents and local automations."""
    return {
        "schema_version": "1.0",
        "project": "opportune",
        "short_command": "uv run opp",
        "principles": ["local-first", "json-friendly", "no external writes by default", "secrets via environment only"],
        "tools": [
            {"name": "start", "command": "uv run opp start", "aliases": ["uv run opp dashboard", "uv run opp dash"], "description": "Start the local dashboard and first-run onboarding at the configured localhost URL.", "safety": "local-server", "output": "foreground FastAPI server"},
            {"name": "doctor", "command": "uv run opp doctor --json", "aliases": ["uv run opp doc --json"], "description": "Check local config, DB, source readiness, and approved-profile setup.", "safety": "read-only", "output": "{ok, summary, checks[]}"},
            {"name": "quickstart", "command": "uv run opp quickstart --json", "aliases": ["uv run opp q --json"], "description": "Create config.yaml if missing and seed demo jobs when empty.", "safety": "local-write", "output": "{ok, created_config, seeded_demo, dashboard_url}"},
            {"name": "config show", "command": "uv run opp config show --json", "description": "Read effective local config/template.", "safety": "read-only", "output": "config object"},
            {"name": "scrape", "command": "uv run opp scrape --json", "description": "Dry-run scraper by default; add --live for local SQLite write.", "safety": "read-only by default; local-write with --live", "output": "scrape result"},
            {"name": "smart scrape", "command": "uv run opp smart --json", "description": "Run small scrape windows and stop when enough high Apply Window jobs are found; add --live to update dashboard SQLite.", "safety": "read-only by default; local-write with --live", "output": "{ok, windows_run, high_apply_windows, dashboard_jobs[]}"},
            {"name": "scheduler", "command": "uv run opp schedule run --once --json", "description": "Run due direct ATS and board discovery tasks with durable state and overlap locking; omit --once for a foreground daemon.", "safety": "local-write", "output": "{ok, ran[], skipped[], state_path}"},
            {"name": "ranking quality", "command": "uv run opp quality --json", "description": "Evaluate the labeled ranking benchmark and release safety gates.", "safety": "read-only", "output": "{ok, metrics, quality_gates, errors[]}"},
            {"name": "update check", "command": "uv run opp update check --json", "description": "Check the latest published GitHub Release without installing it.", "safety": "read-only network", "output": "{ok, checked, current_version, latest_version, update_available, release_url}"},
            {"name": "pool rebuild", "command": "uv run opp jobs rebuild-pool --json", "description": "Materialize configured role+location matches from the local source catalog without scraping again.", "safety": "local-write", "output": "{ok, catalog_active, pool_matches, materialized}"},
            {"name": "jobs list", "command": "uv run opp jobs list --json --limit 20", "aliases": ["uv run opp jobs ls --json"], "description": "List local SQLite jobs with optional status/action/query filters.", "safety": "read-only", "output": "{ok, count, jobs[]}"},
            {"name": "jobs update", "command": "uv run opp jobs update <job_uid> --status watch --note 'review later' --json", "description": "Update local job status/note. No external submission.", "safety": "local-write", "output": "{ok, job}"},

            {"name": "privacy export", "command": "uv run opp privacy export --json", "description": "Export local data to JSON.", "safety": "local-write", "output": "{ok, path}"},
            {"name": "privacy backup", "command": "uv run opp privacy backup --json", "description": "Create local backup ZIP.", "safety": "local-write", "output": "{ok, path}"},
            {"name": "privacy wipe", "command": "uv run opp privacy wipe --confirm WIPE --json", "description": "Clear local job data only after explicit WIPE confirmation.", "safety": "destructive-local", "output": "{ok, message}"},
        ],
    }


def cmd_config(args):
    if args.action == "show":
        _dump(_load_yaml_file(cfg.CONFIG_PATH if cfg.CONFIG_PATH.exists() else cfg.CONFIG_EXAMPLE_PATH), args.json)
        return
    if args.action == "init":
        if cfg.CONFIG_PATH.exists() and not args.force:
            print(f"config already exists: {cfg.CONFIG_PATH} (use --force to overwrite)")
            return
        from public_ops import save_config

        save_config(_load_yaml_file(cfg.CONFIG_EXAMPLE_PATH))
        print(f"created {cfg.CONFIG_PATH}")
        return
    if args.action == "set":
        path = cfg.CONFIG_PATH
        data = _load_yaml_file(path) if path.exists() else _load_yaml_file(cfg.CONFIG_EXAMPLE_PATH)
        keys = args.key.split(".")
        cur = data
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        val: object = args.value
        if args.value.lower() in ("true", "false"):
            val = args.value.lower() == "true"
        elif args.value.isdigit():
            val = int(args.value)
        cur[keys[-1]] = val
        from public_ops import save_config

        save_config(data)
        print(f"wrote {args.key} = {val} to {path}")
        return
    raise SystemExit("unknown config action")


def cmd_scrape(args):
    result = run_scrape(
        live=args.live,
        window=args.window,
        source_group=args.source_group,
    )
    _dump(result, args.json)


def cmd_smart(args):
    _dump(run_smart_scrape(live=args.live, min_high=args.min_high, max_selected=args.max_selected), args.json)


def cmd_schedule(args):
    from pipeline.scheduler import run_forever, run_scheduled_once, scheduler_status

    if args.action == "status":
        _dump(scheduler_status(), args.json)
        return
    if args.once:
        _dump(run_scheduled_once(force=args.force), args.json)
        return
    run_forever()


def cmd_quality(args):
    from ranking.benchmark import evaluate

    report = evaluate()
    _dump(report, args.json)
    if not report["ok"]:
        raise SystemExit(1)


def cmd_run(args):
    from desktop_launcher import run_server_with_browser_launch
    host = args.host or cfg.DASHBOARD_HOST
    port = args.port or cfg.DASHBOARD_PORT
    result = run_server_with_browser_launch(
        host=host,
        port=port,
        no_open=args.no_open,
        browser=args.browser,
        allow_non_loopback=args.allow_non_loopback,
    )
    _dump(result, args.json)
    if not result.get("ok"):
        raise SystemExit(1)


def cmd_desktop(args):
    from desktop_launcher import launch_desktop_app_mode
    host = args.host or cfg.DASHBOARD_HOST
    port = args.port or cfg.DASHBOARD_PORT
    result = launch_desktop_app_mode(
        host=host,
        port=port,
        no_open=args.no_open,
        allow_non_loopback=args.allow_non_loopback,
    )
    _dump(result, args.json)
    if not result.get("ok"):
        raise SystemExit(1)


def cmd_diagnose(args):
    """Explain the latest local discovery funnel without running sources."""
    from dashboard.db import connect, get_discovery_funnel, init_db
    from core.source_quality import summarize_history
    from pipeline.funnel import first_zero_stage

    init_db()
    with connect() as conn:
        funnel = get_discovery_funnel(conn)
    first_zero = first_zero_stage(funnel) if funnel else None
    profile = cfg.get_profile_config()
    _dump(
        {
            "ok": True,
            "first_zero_stage": first_zero,
            "stage": funnel.get("stages", {}).get(first_zero, {}) if first_zero else {},
            "effective_profile": {
                "roles": profile.get("target_roles", []),
                "locations": profile.get("locations", []),
                "max_age_days": int((profile.get("timeline") or {}).get("max_age_days", 7)),
            },
            "funnel": funnel,
            "source_quality": summarize_history(),
        },
        args.json,
    )


def cmd_dashboard(args):
    from dashapi.server import run
    host = args.host or cfg.DASHBOARD_HOST
    port = args.port or cfg.DASHBOARD_PORT
    print(f"Starting dashboard at http://{host}:{port}")
    run(host=host, port=port)


def cmd_audit(args):
    from dashboard import db as dashboard_db
    dashboard_db.init_db()
    with dashboard_db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        by_status = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()}
    report = {
        "db_path": str(dashboard_db.get_db_path()),
        "total_jobs": total,
        "by_status": by_status,
        "enabled_sources": cfg.enabled_sources(),
        "dashboard": {"host": cfg.DASHBOARD_HOST, "port": cfg.DASHBOARD_PORT},
        "config_file": str(cfg.CONFIG_PATH),
    }
    _dump(report, args.json)


def cmd_doctor(args):
    _dump(run_doctor(), args.json)


def cmd_quickstart(args):
    _dump(run_quickstart(seed_demo=not args.no_demo), args.json)


def cmd_tools(args):
    _dump(tools_manifest(), args.json)


def cmd_jobs(args):
    if args.action in ("list", "ls"):
        _dump(run_jobs_list(status=args.status, action_tag=args.action_tag, query=args.query or "", limit=args.limit), args.json)
        return
    if args.action == "update":
        _dump(run_jobs_update(args.job_uid, args.status, args.note), args.json)
        return
    if args.action == "dedupe":
        from dashboard.db import connect, dedupe_jobs

        with connect() as conn:
            removed = dedupe_jobs(conn)
        _dump({"ok": True, "removed_duplicate_rows": removed}, args.json)
        return
    if args.action == "rebuild-pool":
        from dashboard.db import connect, init_db
        from pipeline.discovery_pool import materialize_catalog_pool

        init_db()
        with connect() as conn:
            result = materialize_catalog_pool(conn)
        _dump({"ok": True, **result}, args.json)
        return
    raise SystemExit("unknown jobs action")


def cmd_demo(args):
    from public_ops import seed_demo_data
    _dump(seed_demo_data(clear_first=args.clear), args.json)


def cmd_privacy(args):
    from public_ops import (
        backup_local_state,
        delete_backups,
        export_data,
        full_wipe,
        reset_jobs,
        wipe_local_data,
    )

    if args.action == "export":
        _dump({"ok": True, "path": str(export_data())}, args.json)
    elif args.action == "backup":
        _dump({"ok": True, "path": str(backup_local_state())}, args.json)
    elif args.action == "wipe":
        _dump(wipe_local_data(args.confirm), args.json)
    elif args.action == "reset":
        _dump(reset_jobs(args.confirm), args.json)
    elif args.action == "full-wipe":
        _dump(full_wipe(args.confirm), args.json)
    elif args.action == "delete-backups":
        _dump(delete_backups(args.confirm), args.json)
    else:
        raise SystemExit("unknown privacy action")


def cmd_pilot(args):
    """Manage explicit local pilot metrics; this command never uploads data."""
    from datetime import datetime, timezone

    from pilot_metrics import PilotStore

    store = PilotStore(cfg.JOB_AGENT_HOME / "pilot_metrics.db")
    if args.action == "enable":
        if args.confirm != "ENABLE_LOCAL_PILOT":
            raise SystemExit("pilot enable requires --confirm ENABLE_LOCAL_PILOT")
        session_id = store.enable(consent_version=args.consent_version)
        result = {"ok": True, "enabled": True, "session_id": session_id}
    elif args.action == "inspect":
        result = {"ok": True, **store.inspect()}
    elif args.action == "export":
        cfg.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = cfg.EXPORT_DIR / f"opportune-pilot-{stamp}.json"
        path.write_text(json.dumps(store.export(), indent=2), encoding="utf-8")
        result = {"ok": True, "path": str(path)}
    elif args.action == "disable":
        store.disable()
        result = {"ok": True, "enabled": False}
    elif args.action == "delete":
        if args.confirm != "DELETE_PILOT_METRICS":
            raise SystemExit("pilot delete requires --confirm DELETE_PILOT_METRICS")
        store.delete()
        result = {"ok": True, "deleted": True}
    else:
        raise SystemExit("unknown pilot action")
    _dump(result, args.json)


def cmd_update(args):
    """Check for a newer published Opportune release without installing it."""
    if args.action != "check":
        raise SystemExit("unknown update action")
    from core.update_check import check_for_updates

    _dump(check_for_updates(force=True), args.json)


def cmd_links(args):
    """Backfill link-verification for stored jobs missing a verified date."""
    from dashboard.db import connect, list_jobs, set_link_status
    from core.link_check import verify_job_link

    if args.action != "backfill":
        raise SystemExit("unknown links action")

    with connect() as conn:
        jobs = list_jobs(conn, limit=1000)
        stale = [
            j
            for j in jobs
            if not j.get("is_demo") and j.get("apply_url") and not j.get("link_verified_at")
        ]
        checked = 0
        rejected_dead = 0
        by_status: dict[str, int] = {}
        for job in stale:
            status = verify_job_link(job.get("apply_url"))
            ls = status.get("link_status", "error")
            set_link_status(
                conn, job["job_uid"], ls, status.get("checked_at", "")
            )
            by_status[ls] = by_status.get(ls, 0) + 1
            checked += 1
            # A dead link in the active pipeline is unapplyable — move it
            # to the skip bucket so the dashboard never shows a broken
            # Apply button.
            if ls == "dead" and job.get("action_tag") in ("watch", "apply_now"):
                from dashboard.db import set_job_action_tag

                set_job_action_tag(conn, job["job_uid"], "skip")
                rejected_dead += 1
        result = {
            "ok": True,
            "checked": checked,
            "total_stored": len(jobs),
            "by_status": by_status,
            "rejected_dead_links": rejected_dead,
        }
    _dump(result, args.json)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobhunt", description="Local-first job-hunt automation CLI")
    p.add_argument("--json", action="store_true", help="emit JSON (agent-friendly)")
    sub = p.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("config", aliases=["cfg"], help="show/init/set config.yaml")
    pc.add_argument("action", choices=["show", "init", "set"])
    pc.add_argument("--json", action="store_true", help="emit JSON")
    pc.add_argument("key", nargs="?", help="dotted key, e.g. dashboard.port")
    pc.add_argument("value", nargs="?", help="new value (true/false/int/str)")
    pc.add_argument("--force", action="store_true", help="overwrite existing config.yaml for init")
    pc.set_defaults(func=cmd_config)

    ps = sub.add_parser("scrape", aliases=["s"], help="run the scraper")
    ps.add_argument("--json", action="store_true", help="emit JSON")
    ps.add_argument("--live", action="store_true", help="write to local SQLite (default: dry-run)")
    ps.add_argument("--window", default="morning", help="morning|afternoon|evening")
    ps.add_argument(
        "--source-group",
        choices=["window", "direct", "board"],
        default="window",
        help="window plan, all direct ATS feeds, or all configured board/API feeds",
    )
    ps.set_defaults(func=cmd_scrape)

    smart = sub.add_parser("smart", aliases=["go"], help="smart scrape until enough high Apply Window jobs are found")
    smart.add_argument("--json", action="store_true", help="emit JSON")
    smart.add_argument("--live", action="store_true", help="write dashboard cards to local SQLite")
    smart.add_argument("--min-high", type=int, default=3, help="stop after this many high Apply Window jobs")
    smart.add_argument("--max-selected", type=int, default=15, help="per-window selected-card limit")
    smart.set_defaults(func=cmd_smart)

    schedule = sub.add_parser("schedule", aliases=["scheduler"], help="run or inspect automatic local scraping")
    schedule.add_argument("action", choices=["run", "status"])
    schedule.add_argument("--once", action="store_true", help="run currently due tasks and exit")
    schedule.add_argument("--force", action="store_true", help="run both task groups even when not due")
    schedule.add_argument("--json", action="store_true", help="emit JSON")
    schedule.set_defaults(func=cmd_schedule)

    quality = sub.add_parser("quality", aliases=["benchmark"], help="run labeled ranking quality gates")
    quality.add_argument("--json", action="store_true", help="emit JSON")
    quality.set_defaults(func=cmd_quality)

    pd = sub.add_parser(
        "dashboard",
        aliases=["dash", "start"],
        help="start the web dashboard and first-run onboarding",
    )
    pd.add_argument("--host", default=None)
    pd.add_argument("--port", type=int, default=None)
    pd.set_defaults(func=cmd_dashboard)

    pr = sub.add_parser(
        "run",
        help="start the dashboard server, wait for health, and open default browser",
    )
    pr.add_argument("--host", default=None)
    pr.add_argument("--port", type=int, default=None)
    pr.add_argument("--no-open", action="store_true", help="do not open browser after server ready")
    pr.add_argument("--browser", default=None, help="specific browser to open (e.g., chrome, firefox)")
    pr.add_argument("--allow-non-loopback", action="store_true", help="allow binding to non-loopback hosts (0.0.0.0, etc.)")
    pr.set_defaults(func=cmd_run)

    pdt = sub.add_parser(
        "desktop",
        help="start the dashboard and open in Chrome/Edge/Chromium app mode (maximized); fallback to default browser",
    )
    pdt.add_argument("--host", default=None)
    pdt.add_argument("--port", type=int, default=None)
    pdt.add_argument("--no-open", action="store_true", help="start server only, do not launch app window")
    pdt.add_argument("--allow-non-loopback", action="store_true", help="allow binding to non-loopback hosts (0.0.0.0, etc.)")
    pdt.set_defaults(func=cmd_desktop)

    pdiag = sub.add_parser("diagnose", help="explain where the latest discovery run stopped")
    pdiag.add_argument("--json", action="store_true", help="emit JSON")
    pdiag.set_defaults(func=cmd_diagnose)

    update = sub.add_parser("update", help="check for a newer published Opportune release")
    update.add_argument("action", choices=["check"])
    update.add_argument("--json", action="store_true", help="emit JSON")
    update.set_defaults(func=cmd_update)

    pa = sub.add_parser("audit", help="pipeline health check")
    pa.add_argument("--json", action="store_true", help="emit JSON")
    pa.set_defaults(func=cmd_audit)

    doc = sub.add_parser("doctor", aliases=["doc"], help="local setup and readiness check")
    doc.add_argument("--json", action="store_true", help="emit JSON")
    doc.set_defaults(func=cmd_doctor)

    quick = sub.add_parser("quickstart", aliases=["q"], help="create config and seed demo jobs if empty")
    quick.add_argument("--json", action="store_true", help="emit JSON")
    quick.add_argument("--no-demo", action="store_true", help="do not seed demo jobs")
    quick.set_defaults(func=cmd_quickstart)

    tools = sub.add_parser("tools", help="emit agent-friendly command manifest")
    tools.add_argument("--json", action="store_true", help="emit JSON")
    tools.set_defaults(func=cmd_tools)

    jobs = sub.add_parser("jobs", help="list or update local jobs")
    jobs.add_argument("action", choices=["list", "ls", "update", "dedupe", "rebuild-pool"])
    jobs.add_argument("job_uid", nargs="?", help="required for update")
    jobs.add_argument("--json", action="store_true", help="emit JSON")
    jobs.add_argument("--status", default=None, help="status filter for list; new status for update")
    jobs.add_argument("--action-tag", default=None, help="action_tag filter for list")
    jobs.add_argument("--query", default="", help="text query for list")
    jobs.add_argument("--limit", type=int, default=50)
    jobs.add_argument("--note", default=None)
    jobs.set_defaults(func=cmd_jobs)

    demo = sub.add_parser("demo", help="load sample demo jobs")
    demo.add_argument("--json", action="store_true", help="emit JSON")
    demo.add_argument("--clear", action="store_true", help="clear existing jobs first")
    demo.set_defaults(func=cmd_demo)

    priv = sub.add_parser("privacy", help="export, backup, reset, or wipe local data")
    priv.add_argument("--json", action="store_true", help="emit JSON")
    priv.add_argument(
        "action",
        choices=["export", "backup", "wipe", "reset", "full-wipe", "delete-backups"],
    )
    priv.add_argument(
        "--confirm",
        default="",
        help="exact confirmation required for destructive actions",
    )
    priv.set_defaults(func=cmd_privacy)

    pilot = sub.add_parser("pilot", help="manage opt-in local pilot metrics")
    pilot.add_argument("--json", action="store_true", help="emit JSON")
    pilot.add_argument("action", choices=["enable", "inspect", "export", "disable", "delete"])
    pilot.add_argument("--consent-version", default="1.0")
    pilot.add_argument("--confirm", default="")
    pilot.set_defaults(func=cmd_pilot)

    links = sub.add_parser("links", help="verify stored job apply URLs")
    links.add_argument(
        "action",
        choices=["backfill"],
        help="re-check every stored job with no link_verified_at and persist results",
    )
    links.add_argument("--json", action="store_true", help="emit JSON")
    links.set_defaults(func=cmd_links)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if getattr(args, "action", None) == "update" and not getattr(args, "job_uid", None):
        raise SystemExit("jobs update requires job_uid")
    if getattr(args, "action", None) == "update" and not getattr(args, "status", None):
        raise SystemExit("jobs update requires --status")
    args.func(args)


if __name__ == "__main__":
    main()
