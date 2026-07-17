"""Keep all tests isolated from ignored developer runtime state."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_local_runtime_state(tmp_path, monkeypatch):
    import config
    import anyio.to_thread
    import fastapi.routing
    from core import source_health, source_registry
    from dashboard import db
    from onboarding import providers
    from resume import resume_profile

    runtime = tmp_path / "runtime"
    project_root = Path(__file__).resolve().parents[1]
    runtime_resume = runtime / "resume"
    runtime_resume.mkdir(parents=True, exist_ok=True)
    (runtime / "config.yaml").write_text(
        "profile:\n"
        "  locations: [United States, Remote US]\n"
        "  timeline: {max_age_days: 7}\n"
        "sources: []\n",
        encoding="utf-8",
    )
    shutil.copyfile(
        project_root / "resume" / "resume_profile.md",
        runtime_resume / "resume_profile.md",
    )
    shutil.copyfile(
        project_root / "candidate_profile.yaml",
        runtime / "candidate_profile.yaml",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", runtime / "config.yaml")
    config._CONFIG_CACHE_KEY = None
    config._CONFIG_CACHE_VALUE = None

    async def run_sync_inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def anyio_sync_inline(
        func,
        *args,
        abandon_on_cancel=False,
        cancellable=None,
        limiter=None,
    ):
        del abandon_on_cancel, cancellable, limiter
        return func(*args)

    # The managed test sandbox blocks AnyIO's worker-thread portal. Route
    # functions still run through the full ASGI stack, but execute inline in
    # tests so HTTP middleware and validation remain covered deterministically.
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", run_sync_inline)
    monkeypatch.setattr(anyio.to_thread, "run_sync", anyio_sync_inline)
    db.set_db_path(runtime / "dashboard.db")
    providers.set_provider_paths(
        runtime / "onboarding" / "llm.json",
        runtime / "onboarding" / "llm.key",
    )
    monkeypatch.setattr(source_health, "DEFAULT_HEALTH_PATH", runtime / "source_health.json")
    monkeypatch.setattr(source_registry, "_LOCAL_REGISTRY_PATH", runtime / "source_registry.yaml")
    monkeypatch.setattr(resume_profile, "_PROFILE_PATH", runtime_resume / "resume_profile.md")
    monkeypatch.setattr(resume_profile, "_CANDIDATE_PROFILE_PATH", runtime / "candidate_profile.yaml")
    resume_profile._profile = None
    resume_profile._candidate_preferences = None
    yield
    db.set_db_path(None)
    config._CONFIG_CACHE_KEY = None
    config._CONFIG_CACHE_VALUE = None
    resume_profile._profile = None
    resume_profile._candidate_preferences = None
