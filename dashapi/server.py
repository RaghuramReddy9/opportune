"""dashapi/server.py — local FastAPI server for the job-hunt dashboard.

Serves a single-page UI and a small JSON API. All reads/writes go through
dashboard.db (SQLite). No external calls from the UI except to this server.
Run: uv run --with fastapi --with uvicorn python dashapi/server.py
"""
# ruff: noqa: E402 -- direct script execution needs PROJECT_ROOT on sys.path.
from __future__ import annotations

import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

# Ensure the project root is importable when running as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from public_ops import (
    backup_local_state,
    export_data,
    load_config,
    save_config,

    seed_demo_data,
    wipe_local_data,
)

from dashboard.db import (
    connect,

    get_active_profile,
    get_dashboard_model,
    get_db_path,
    get_enrichment_backlog,
    get_catalog_stats,
    get_latest_scrape_run,
    init_db,
    list_jobs,
    list_profiles,
    set_active_profile,
    set_job_action_tag,
    set_job_note,
    set_job_status,
    stats_for_profile,
    upsert_scraped_job,
)
from core.source_health import load_health
from pipeline.scrape import scrape_all
from pipeline.smart_scrape import smart_scrape
from onboarding.providers import (
    ProviderConfigStore,
    normalize_provider_settings,
    test_provider_connection,
)
from onboarding.resume_reader import extract_resume_text
from onboarding.service import OnboardingService


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Ensure the dashboard DB exists before serving requests.
    init_db()
    yield


app = FastAPI(title="Opportune", version="0.1.0", lifespan=_lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"],
)


@app.middleware("http")
async def _protect_local_mutations(request: Request, call_next):
    """Reject browser mutations originating outside the local dashboard."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urlparse(origin)
            origin_host = (parsed_origin.hostname or "").lower()
            request_host = (request.url.hostname or "").lower()
            try:
                origin_port = parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
            except ValueError:
                origin_port = -1
            request_port = request.url.port or (443 if request.url.scheme == "https" else 80)
            same_origin = (
                parsed_origin.scheme == request.url.scheme
                and origin_host == request_host
                and origin_port == request_port
            )
            if origin_host not in {"127.0.0.1", "localhost", "::1"} or not same_origin:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "local API rejects cross-origin mutations"},
                )
    return await call_next(request)

class ConfigUpdate(BaseModel):
    config: dict


class ResumeTextUpload(BaseModel):
    text: str = Field(min_length=20, max_length=2_000_000)
    filename: str = Field(default="resume.txt", min_length=1, max_length=120)


class ProviderUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=10_000)
    requires_api_key: bool | None = None


class OnboardingAnswers(BaseModel):
    answers: dict


class WipeRequest(BaseModel):
    confirm: str

class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


class NoteUpdate(BaseModel):
    note: str


VALID_STATUSES = {
    "discovered",
    "watch",
    "applied",
    "confirmed",
    "interview",
    "assessment",
    "offer",
    "rejected",
    "closed",
}


def _require_approved_profile() -> dict:
    active = get_active_profile()
    if not active:
        raise HTTPException(
            status_code=409,
            detail="Complete onboarding and approve your search plan before running discovery.",
        )
    return active


_SECRET_QUERY_RE = re.compile(
    r"([?&](?:api[_-]?key|access[_-]?token|token|secret|password)=)[^&\s]+",
    re.IGNORECASE,
)


def _redact_health_secrets(value):
    """Redact credential-like query parameters before returning health JSON."""
    if isinstance(value, str):
        return _SECRET_QUERY_RE.sub(r"\1[redacted]", value)
    if isinstance(value, list):
        return [_redact_health_secrets(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_health_secrets(item) for key, item in value.items()}
    return value


@app.get("/api/health")
def health():
    """Return service health, DB stats, source health, and enrichment backlog."""
    try:
        with connect() as conn:
            active = get_active_profile()
            profile_id = active["profile_id"] if active else None
            model = get_dashboard_model(conn, profile_id=profile_id)
            backlog = get_enrichment_backlog(conn, limit=1)
            catalog = get_catalog_stats(conn)
            latest_scrape = get_latest_scrape_run(conn)
            db_size = Path(get_db_path()).stat().st_size if Path(get_db_path()).exists() else 0
        source_health = _redact_health_secrets(load_health())
        return {
            "ok": True,
            "service": "opportune",

            "dashboard": {
                "total_jobs": model.get("stats", {}).get("total", 0),
                "apply_now": model.get("stats", {}).get("apply_now", 0),
                "watch": model.get("stats", {}).get("watch", 0),
            },
            "db_size_bytes": db_size,
            "enrichment_backlog": len(backlog),
            "source_health": source_health,
            "catalog": catalog,
            "latest_scrape": latest_scrape,
            "scheduler": __import__("pipeline.scheduler", fromlist=["scheduler_status"]).scheduler_status(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"health check failed: {exc}") from exc


@app.post("/api/enrichment/backfill")
def api_enrichment_backfill(limit: int = 50):
    """Process pending enrichment queue jobs and return a summary."""
    try:
        from core.job_description import backfill_enrichment
        summary = backfill_enrichment(limit=min(limit, 200))
        return {"ok": True, **summary}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"enrichment backfill failed: {exc}") from exc


@app.get("/api/config")
def api_get_config():
    return {"ok": True, "config": load_config()}


@app.get("/api/quality")
def api_quality():
    from ranking.benchmark import evaluate

    return evaluate()


@app.post("/api/config")
def api_save_config(body: ConfigUpdate):
    try:
        return save_config(body.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/onboarding")
def api_onboarding_status():
    """Return resumable first-run state without resume text or API keys."""
    return OnboardingService().status()


@app.get("/api/onboarding/provider")
def api_onboarding_provider():
    return {"ok": True, "provider": ProviderConfigStore().public_settings()}


@app.post("/api/onboarding/provider")
def api_save_onboarding_provider(body: ProviderUpdate):
    try:
        settings = normalize_provider_settings(body.model_dump())
        provider = ProviderConfigStore().save(settings, api_key=body.api_key)
        return {"ok": True, "provider": provider}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/onboarding/provider/test")
def api_test_onboarding_provider():
    try:
        return test_provider_connection()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to that model. Check the base URL, model, and key.",
        ) from exc


@app.post("/api/onboarding/analyze")
def api_analyze_onboarding_resume(body: ResumeTextUpload):
    try:
        return OnboardingService().analyze_resume(body.text, filename=body.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Resume analysis failed. Check your model connection and try again.",
        ) from exc


@app.post("/api/onboarding/upload")
async def api_upload_onboarding_resume(file: UploadFile = File(...)):
    try:
        content = await file.read()
        filename = file.filename or "resume.txt"
        text = extract_resume_text(filename, content)
        return OnboardingService().analyze_resume(text, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Resume analysis failed. Check your model connection and try again.",
        ) from exc


@app.post("/api/onboarding/{session_id}/answers")
def api_submit_onboarding_answers(session_id: str, body: OnboardingAnswers):
    try:
        return OnboardingService().submit_answers(session_id, body.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/onboarding/{session_id}/approve")
def api_approve_onboarding(session_id: str):
    try:
        return OnboardingService().approve(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/profiles")
def api_list_profiles():
    """Return all stored profiles (id, name, is_active, timestamps)."""
    return {"ok": True, "profiles": list_profiles()}


@app.post("/api/profiles/{profile_id}/activate")
def api_activate_profile(profile_id: str):
    """Switch the active profile so the next scrape uses it."""
    ok = set_active_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="profile not found")
    return {"ok": True, "profile_id": profile_id}


@app.post("/api/demo")
def api_demo(clear_first: bool = False):
    return seed_demo_data(clear_first=clear_first)


@app.post("/api/privacy/wipe")
def api_wipe(body: WipeRequest):
    try:
        return wipe_local_data(body.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/privacy/export")
def api_export():
    return {"ok": True, "path": str(export_data())}


@app.post("/api/privacy/backup")
def api_backup():
    return {"ok": True, "path": str(backup_local_state())}


@app.get("/api/dashboard")
def api_dashboard():
    with connect() as conn:
        active = get_active_profile()
        profile_id = active["profile_id"] if active else None
        real_model = get_dashboard_model(conn, profile_id=profile_id)
        model = (
            real_model
            if active or real_model["stats"]["total"]
            else get_dashboard_model(conn, include_demo=True)
        )
        # Attach per-profile stats when an active profile exists.
        if active:
            model["profile"] = {
                "profile_id": active["profile_id"],
                "name": active["name"],
                **stats_for_profile(conn, active["profile_id"]),
            }
        return model


@app.get("/api/jobs")
def api_jobs(status: str | None = None, action_tag: str | None = None, limit: int = 300):
    active = get_active_profile()
    profile_id = active["profile_id"] if active else None
    with connect() as conn:
        return list_jobs(
            conn,
            status=status,
            action_tag=action_tag,
            profile_id=profile_id,
            limit=limit,
        )


@app.post("/api/jobs/{job_uid:path}/status")
def api_set_status(job_uid: str, body: StatusUpdate):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {body.status}")
    with connect() as conn:
        ok = set_job_status(conn, job_uid, body.status, note=body.note)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job_uid": job_uid, "status": body.status}


@app.post("/api/jobs/{job_uid:path}/note")
def api_set_note(job_uid: str, body: NoteUpdate):
    with connect() as conn:
        ok = set_job_note(conn, job_uid, body.note)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job_uid": job_uid}


@app.post("/api/scrape")
def api_scrape(dry_run: bool = True):
    """Run the scraper on demand from the dashboard."""
    _require_approved_profile()
    result = scrape_all(max_selected=15, dry_run=dry_run)
    with connect() as conn:
        if not dry_run:
            _sync_dashboard_jobs(conn, result.get("dashboard_jobs", []))
        active = get_active_profile()
        model = get_dashboard_model(
            conn,
            profile_id=active["profile_id"] if active else None,
        )
    return {"ok": True, "raw_count": result.get("raw_count", 0), "dashboard": model}


def _sync_dashboard_jobs(conn, dashboard_jobs: list[dict]) -> None:
    """Upsert scrape results, skipping excluded jobs, then verify links.

    Excluded (action_tag == 'skip') jobs are never stored. For every other
    job we upsert without inline checks (fast bulk write) and then run the
    link liveness check so the dashboard never shows unverified Apply buttons.
    """
    from core.link_check import verify_job_link
    from dashboard.db import set_link_status

    for job in dashboard_jobs:
        if job.get("action_tag") == "skip":
            # Do not insert newly excluded jobs, but demote a legacy active row
            # when fresh employer text reveals a blocker.
            company = (job.get("company") or "").strip().lower()
            title = (job.get("title") or job.get("role") or "").strip().lower()
            profile_id = str(job.get("profile_id") or "").strip()
            if company and title:
                existing = conn.execute(
                    "SELECT job_uid FROM jobs "
                    "WHERE LOWER(TRIM(company)) = ? AND LOWER(TRIM(title)) = ? "
                    "AND COALESCE(profile_id, '') = ?",
                    (company, title, profile_id),
                ).fetchone()
                if existing:
                    set_job_action_tag(conn, existing["job_uid"], "skip")
            continue
        uid = upsert_scraped_job(conn, job, check_links=False)
        # Broad pool ingestion may contain hundreds of rows. Link checks are a
        # separate backfill concern and must not serialize discovery on network
        # requests before the user can browse the local pool.
        if job.get("action_tag") == "pool" or job.get("is_demo") or not job.get("apply_url"):
            continue
        try:
            status = verify_job_link(job.get("apply_url"))
            set_link_status(
                conn, uid,
                status.get("link_status", "error"),
                status.get("checked_at", ""),
            )
        except Exception:
            set_link_status(conn, uid, "error", "")


@app.post("/api/pool/rebuild")
def api_rebuild_pool():
    """Materialize configured role+location matches from the local catalog."""
    _require_approved_profile()
    from pipeline.discovery_pool import materialize_catalog_pool

    with connect() as conn:
        result = materialize_catalog_pool(conn)
        active = get_active_profile()
        model = get_dashboard_model(
            conn,
            profile_id=active["profile_id"] if active else None,
        )
    return {"ok": True, **result, "dashboard": model}


@app.post("/api/smart-scrape")
def api_smart_scrape(live: bool = True, min_high: int = 3):
    """Run Smart Scrape from the dashboard and update local SQLite by default."""
    _require_approved_profile()
    result = smart_scrape(live=live, min_high=min_high)
    with connect() as conn:
        if live:
            _sync_dashboard_jobs(conn, result.get("dashboard_jobs", []))
        active = get_active_profile()
        model = get_dashboard_model(
            conn,
            profile_id=active["profile_id"] if active else None,
        )
    return {
        "ok": True,
        "raw_count": result.get("raw_count", 0),
        "windows_run": result.get("windows_run", []),
        "high_apply_windows": result.get("high_apply_windows", 0),
        "stopped_reason": result.get("stopped_reason"),
        "dashboard": model,
    }


# Serve the working-tree build during development and packaged data after install.
_PROJECT_FRONTEND_DIR = _PROJECT_ROOT / "frontend" / "dist"
_INSTALLED_FRONTEND_DIR = Path(sys.prefix) / "frontend" / "dist"


def _resolve_frontend_dir(project_dir: Path, installed_dir: Path) -> Path:
    return project_dir if (project_dir / "index.html").exists() else installed_dir


FRONTEND_DIR = _resolve_frontend_dir(_PROJECT_FRONTEND_DIR, _INSTALLED_FRONTEND_DIR)


@app.get("/assets/{asset_path:path}")
def frontend_asset(asset_path: str):
    fp = (FRONTEND_DIR / "assets" / asset_path).resolve()
    assets_root = (FRONTEND_DIR / "assets").resolve()
    if assets_root not in fp.parents or not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(fp)


@app.get("/favicon.svg")
def favicon():
    fp = FRONTEND_DIR / "favicon.svg"
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(fp)


@app.get("/icons.svg")
def icons():
    fp = FRONTEND_DIR / "icons.svg"
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(fp)


@app.get("/", response_class=HTMLResponse)
def index():
    fp = FRONTEND_DIR / "index.html"
    if fp.exists():
        return HTMLResponse(fp.read_text())
    return HTMLResponse("<h1>Opportune</h1><p>Build the frontend: cd frontend && npm run build</p>")


# Catch-all for SPA routes (e.g. /pipeline, /settings).
@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_catch_all(full_path: str):
    # Only serve index.html for non-API, non-asset paths.
    if full_path.startswith("api/") or full_path.startswith("docs"):
        raise HTTPException(status_code=404)
    fp = FRONTEND_DIR / "index.html"
    if fp.exists():
        return HTMLResponse(fp.read_text())
    return HTMLResponse("<h1>Opportune</h1><p>Build the frontend first.</p>")


def run(host: str = "127.0.0.1", port: int = 8770) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
