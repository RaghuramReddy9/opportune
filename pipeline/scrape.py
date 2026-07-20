"""
pipeline/scrape.py — Parallel job scraping orchestrator.

Runs all enabled sources concurrently, then merges results.
Replaces the sequential scraper.py.
"""
import logging
import re
import time
import json
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Any

from core.source_registry import (
    load_registry, get_enabled_companies, get_companies_by_ats,
    get_unknown_ats_companies, can_run_apify,
)
from ranking import filter_and_rank
from ranking.score import _plausible_ranking_candidate, rank_job
from ranking.guardrails import apply_freshness_trust, freshness_sort_rank
from ranking.eligibility import evaluate_ready_to_apply
from ranking.targeting import classify_role_families, classify_target_level
from core.http import sanitize_url
from pipeline.funnel import new_funnel, record_stage
from pipeline.query_strategy import get_default_query_corpus
from profile_context import get_approved_profile_context

logger = logging.getLogger("pipeline.scrape")


def _log_event(event: str, **fields: Any) -> None:
    """Structured JSON-ish log event for cron parseability."""
    payload = {"event": event, **fields}
    logger.info("%s", json.dumps(payload, ensure_ascii=False))


_MAX_SOURCE_RETRIES = 3
_SOURCE_RETRY_BASE_DELAY = 1.0
_MAX_SCRAPE_SECONDS = 600
_COMPLETE_SNAPSHOT_SOURCES = frozenset({"greenhouse", "lever", "ashby", "workable"})


def _persist_direct_source_snapshots(
    completed_tasks: list[tuple],
    *,
    run_window: str,
) -> dict:
    """Persist successful complete ATS snapshots in the shared local database.

    Query-based boards and aggregators are intentionally excluded: a rotated
    query returning no job does not prove that a listing closed. Direct ATS
    company feeds are complete snapshots and can safely drive lifecycle state.
    """
    from dashboard.db import (
        connect,
        finish_scrape_run,
        get_catalog_stats,
        init_db,
        reconcile_source_snapshot,
        start_scrape_run,
    )

    init_db()
    summaries = []
    with connect() as conn:
        run_id = start_scrape_run(conn, run_window)
        listing_count = 0
        for source_key, source_name, scrape_result in completed_tasks:
            if source_key not in _COMPLETE_SNAPSHOT_SOURCES or scrape_result.get("error"):
                continue
            jobs = scrape_result.get("jobs", [])
            summary = reconcile_source_snapshot(
                conn,
                run_id=run_id,
                source_key=source_key,
                source_name=source_name,
                jobs=jobs,
            )
            summaries.append(summary)
            listing_count += int(summary["observed"])
        finish_scrape_run(
            conn,
            run_id,
            source_count=len(summaries),
            listing_count=listing_count,
        )
        catalog_stats = get_catalog_stats(conn)
    return {
        "run_id": run_id,
        "sources_reconciled": len(summaries),
        "listings_observed": listing_count,
        "source_summaries": summaries,
        "states": catalog_stats,
    }


def _is_transient_error(error: BaseException) -> bool:
    """Heuristic: transient network/HTTP errors are retryable."""
    message = str(error).lower()
    return any(token in message for token in (
        "timeout", "timed out", "connection", "name resolution", "temporary",
        "502", "503", "504", "ssl", "remote end closed", "broken pipe",
    ))


def _scrape_with_retry(func, arg, *, retries: int = _MAX_SOURCE_RETRIES) -> dict:
    """Call a scrape function with exponential backoff on transient failures."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return func(arg) if arg is not None else func()
        except Exception as e:
            last_error = e
            if attempt < retries and _is_transient_error(e):
                delay = _SOURCE_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning("  ⏳ %s attempt %d/%d failed: %s — retrying in %.1fs",
                               getattr(func, "__name__", "scrape"), attempt, retries, e, delay)
                time.sleep(delay)
            else:
                break
    return {"jobs": [], "raw_count": 0, "error": str(last_error)}


def _submit_tasks(executor, tasks):
    """Submit scrape tasks. Returns {future: (source_key, name)}."""
    future_to_task = {}
    for source_key, name, func, arg in tasks:
        future = executor.submit(_scrape_with_retry, func, arg)
        future_to_task[future] = (source_key, name)
    return future_to_task


def _execute_source_tasks(tasks: list[tuple], *, max_workers: int, timeout_seconds: float) -> tuple[list[tuple], list[dict], list[dict]]:
    """Run source tasks within one global deadline.

    Returns completed ``(source, company, result)`` tuples, failures, and
    sources skipped by the persistent circuit breaker.
    """
    from core.source_health import (
        filter_runnable_tasks,
        record_source_failure,
        record_source_success,
    )

    runnable, skipped = filter_runnable_tasks(tasks)
    completed: list[tuple] = []
    failures: list[dict] = []
    executor = ThreadPoolExecutor(max_workers=max_workers)
    pending = _submit_tasks(executor, runnable)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, _ = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                source_key, name = pending.pop(future)
                try:
                    scrape_result = future.result()
                except Exception as exc:
                    scrape_result = {"jobs": [], "raw_count": 0, "error": str(exc)}
                error = scrape_result.get("error")
                try:
                    if error:
                        record_source_failure(source_key, name, error)
                    else:
                        record_source_success(source_key, name, len(scrape_result.get("jobs", [])))
                except OSError as exc:
                    logger.warning("Could not persist source health for %s: %s", source_key, exc)
                completed.append((source_key, name, scrape_result))

        for future, (source_key, name) in list(pending.items()):
            future.cancel()
            error = f"scrape timed out after {timeout_seconds:g}s"
            try:
                record_source_failure(source_key, name, error)
            except OSError as exc:
                logger.warning("Could not persist timeout health for %s: %s", source_key, exc)
            failures.append({"source": source_key, "company": name, "error": error})
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return completed, failures, skipped

# ── Source adapter functions ──
# Each returns {"jobs": [...], "raw_count": int, "error": str|None}

def _scrape_greenhouse(company: dict) -> dict:
    """Scrape a single Greenhouse company."""
    from adapters.greenhouse_adapter import scrape
    return scrape(company["company_name"], company["ats_slug"], company.get("ats_url", ""))

def _scrape_lever(company: dict) -> dict:
    """Scrape a single Lever company."""
    from adapters.lever_adapter import scrape
    return scrape(company["company_name"], company["ats_slug"], company.get("ats_url", ""))

def _scrape_ashby(company: dict) -> dict:
    """Scrape a single Ashby company."""
    from adapters.ashby_adapter import scrape
    return scrape(company["company_name"], company["ats_slug"], company.get("ats_url", ""))

def _scrape_workable(company: dict) -> dict:
    """Scrape a single Workable public careers feed."""
    from adapters.workable_adapter import scrape
    return scrape(company["company_name"], company["ats_slug"], company.get("ats_url", ""))

def _scrape_github_lists() -> dict:
    """Scrape GitHub curated lists."""
    from adapters.github_lists_adapter import scrape
    return scrape()

def _scrape_ycombinator() -> dict:
    """Scrape Y Combinator."""
    from adapters.ycombinator_adapter import scrape
    return scrape()

def _merge_duplicate_job(existing: dict, incoming: dict) -> None:
    """Merge duplicate-source metadata without losing early-career signals.

    Direct ATS sources often finish before curated GitHub new-grad lists. If the
    same apply URL appears twice, the curated list may be the only source whose
    title contains `New Grad`, `Engineer I`, or `Junior`. Preserve that signal so
    ranking does not incorrectly discard the job as an unknown-level duplicate.
    """
    aliases = set(existing.get("source_aliases", []))
    if existing.get("source"):
        aliases.add(existing["source"])
    if incoming.get("source"):
        aliases.add(incoming["source"])
    existing["source_aliases"] = sorted(aliases)

    existing_level = classify_target_level(existing.get("title", ""))
    incoming_level = classify_target_level(incoming.get("title", ""))
    early_levels = {"new_grad", "entry_level", "junior", "associate", "engineer_i", "zero_to_two_years", "early_career"}

    incoming_has_better_level = incoming_level in early_levels and existing_level not in early_levels
    incoming_is_curated_level_source = incoming.get("source") == "github_list" and incoming_level in early_levels

    if incoming_has_better_level or incoming_is_curated_level_source:
        for field in ("title", "company", "location", "department", "employment_type", "posted_date", "freshness", "source", "ats_type", "ats_slug"):
            if incoming.get(field):
                existing[field] = incoming[field]

    # Keep the richest text from either source for eligibility and reporting.
    for field in ("description", "full_text"):
        if len(str(incoming.get(field, ""))) > len(str(existing.get(field, ""))):
            existing[field] = incoming[field]


# ── Query rotation for API sources ──
# Rotates through targeted role-family queries by scraper time window.
_ROLE_FAMILY_QUERIES = get_default_query_corpus()
_ACTIVE_WINDOW = "morning"


def _get_daily_query(offset: int = 0) -> str:
    """Return a targeted query for the active morning/afternoon/evening window."""
    from pipeline.query_strategy import get_query
    return get_query(_ACTIVE_WINDOW, offset=offset)


def _scrape_jsearch() -> dict:
    """Scrape JSearch (OpenWebNinja) with a daily rotating role-family query."""
    from adapters.jsearch_adapter import scrape
    query = _get_daily_query(offset=0)
    logger.info("JSearch daily query: '%s'", query)
    return scrape(query=query, location="United States", num_pages=1)

def _scrape_adzuna() -> dict:
    """Scrape Adzuna with a daily rotating role-family query (offset by 7 for diversity)."""
    from adapters.adzuna_adapter import scrape
    query = _get_daily_query(offset=7)
    logger.info("Adzuna daily query: '%s'", query)
    return scrape(query=query, country="us", max_results=50)

def _scrape_serpapi() -> dict:
    """Scrape SerpApi (Google Jobs). Rotates queries and silently skips if quota exhausted."""
    from adapters.serpapi_adapter import scrape
    query = _get_daily_query(offset=3)  # Different offset from JSearch and Adzuna
    result = scrape(query=query, location="United States")
    # If quota exhausted, silently return empty
    if result.get("error") and "429" in result["error"]:
        return {"jobs": [], "raw_count": 0, "error": None}
    return result

def _scrape_apify(company: dict) -> dict:
    """Scrape via Apify fallback."""
    from adapters.apify_fallback_adapter import scrape_workday
    return scrape_workday(company["company_name"], company.get("career_url", ""))

def _scrape_builtin() -> dict:
    """Scrape Built In tech job board via JSON-LD structured data."""
    from adapters.builtin_adapter import scrape
    return scrape(max_urls=3)

def _scrape_wellfound() -> dict:
    """Scrape Wellfound startup jobs."""
    from adapters.wellfound_adapter import scrape
    return scrape(max_urls=3)


APPLY_NOW_MIN_SCORE = 82
WATCH_MIN_SCORE = 55
APPLY_NOW_BLOCKING_CAPS = {
    "unknown_location_cap",
    "location_rejected_cap",
    "unknown_auth_cap",
    "unknown_level_cap",
    "thin_description_cap",
    "no_applied_ai_family_cap",
}


def enrich_candidates_before_eligibility(jobs: list[dict]) -> int:
    """Fetch candidate descriptions before the eligibility truth gate.

    Employer-page text can contain hard blockers (citizenship, clearance,
    sponsorship, experience) that are absent from board snippets. Enrichment
    is parallelized by ``enrich_jobs_with_details`` and bounded to this pool.
    """
    if not jobs:
        return 0
    from core.job_description import enrich_jobs_with_details

    return enrich_jobs_with_details(jobs, max_jobs=len(jobs))


def filter_ready_to_apply_jobs(jobs: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split candidates into ready, needs-review, and excluded jobs."""
    from resume.resume_profile import load_candidate_preferences

    ready = []
    needs_review = []
    excluded = []
    preferences = load_candidate_preferences()
    visa_policy = str(preferences.get("visa_policy") or "custom").lower()
    sponsorship_confirmation_required = visa_policy in {
        "needs_sponsorship",
        "opt_cpt",
        "custom",
    }

    for job in jobs:
        if job.get("excluded"):
            job["ready_to_apply"] = False
            job["eligibility_severity"] = "excluded"
            job["eligibility_reason_codes"] = ["ranking_excluded"]
            job["eligibility_reasons"] = [
                f"Ranking exclusion: {job.get('exclude_reason') or 'role outside configured target'}"
            ]
            excluded.append(job)
            continue
        eligibility = evaluate_ready_to_apply(job)
        job["ready_to_apply"] = eligibility["ready_to_apply"]
        job["eligibility_severity"] = eligibility["severity"]
        job["eligibility_reason_codes"] = eligibility["reason_codes"]
        job["eligibility_reasons"] = eligibility["reasons"]

        if eligibility["ready_to_apply"]:
            has_scoring_metadata = any(key in job for key in ("resume_match_score", "score_caps", "location_verdict"))
            if not has_scoring_metadata:
                ready.append(job)
                continue
            score = int(job.get("resume_match_score", 0) or 0)
            caps = set(job.get("score_caps", []))
            location_status = (job.get("location_verdict") or {}).get("status")
            if location_status not in {"us_verified", "configured_verified"}:
                job["ready_to_apply"] = False
                job["eligibility_severity"] = "excluded"
                job["eligibility_reason_codes"].append("location_not_verified")
                job["eligibility_reasons"].append("Hidden until U.S./Remote-U.S. location is verified.")
                excluded.append(job)
            elif job.get("freshness_trust") != "confirmed_posted_date":
                job["ready_to_apply"] = False
                job["eligibility_severity"] = "needs_review"
                job["eligibility_reason_codes"].append("posting_date_unverified")
                job["eligibility_reasons"].append(
                    "Posting date is unverified; keep in Watch instead of Apply Now."
                )
                needs_review.append(job)
            elif sponsorship_confirmation_required and job.get("opt_signal") != "Strong":
                job["ready_to_apply"] = False
                job["eligibility_severity"] = "needs_review"
                job["eligibility_reason_codes"].append("sponsorship_not_confirmed")
                job["eligibility_reasons"].append(
                    "Sponsorship/OPT support is not explicit; verify it before applying."
                )
                needs_review.append(job)
            elif score < APPLY_NOW_MIN_SCORE:
                job["ready_to_apply"] = False
                job["eligibility_severity"] = "needs_review"
                job["eligibility_reason_codes"].append("score_below_apply_threshold")
                job["eligibility_reasons"].append(f"Score {score} is below Apply Now threshold {APPLY_NOW_MIN_SCORE}.")
                needs_review.append(job)
            elif caps & APPLY_NOW_BLOCKING_CAPS:
                job["ready_to_apply"] = False
                job["eligibility_severity"] = "needs_review"
                job["eligibility_reason_codes"].append("apply_now_evidence_incomplete")
                job["eligibility_reasons"].append("Missing authorization, level, or description confidence for Apply Now.")
                needs_review.append(job)
            else:
                ready.append(job)
        elif eligibility["severity"] == "needs_review":
            needs_review.append(job)
        else:
            excluded.append(job)

    return ready, needs_review, excluded


def _job_url(job: dict) -> str:
    return str(job.get("apply_url") or job.get("raw_url") or "").strip()


def _within_timeline(job: dict, max_age_days: int) -> bool:
    """Keep unknown-age jobs for review and enforce the configured dated window."""
    from core.freshness import get_age_days

    age_days = get_age_days(job)
    return age_days < 0 or age_days <= max_age_days


def _has_negated_ai_context(job: dict) -> bool:
    """Reject obvious 'not AI' text so negated keywords don't create Watch noise."""
    text = "\n".join(str(job.get(field, "")) for field in ("title", "description", "full_text", "details") if job.get(field)).lower()
    return any(
        phrase in text
        for phrase in (
            "no ai",
            "no llm",
            "no rag",
            "without ai",
            "without llm",
            "without rag",
            "not ai",
            "not llm",
            "not rag",
        )
    )


def _is_off_target_watch_title(job: dict) -> bool:
    """Reject known non-engineering security/research titles from Watch."""
    title = str(job.get("title") or job.get("role") or "").strip().lower()
    return bool(re.search(r"\bsecurity\s+researcher\b", title)) or bool(
        re.search(r"\b(?:security\s+)?compliance\s+analyst\b", title)
    )


def build_watch_candidates(
    raw_jobs: list[dict],
    already_selected: list[dict],
    limit: int = 15,
    max_age_days: int | None = None,
) -> list[dict]:
    """Build a broader Watch pool from near-matches before strict ranking drops them.

    Apply Now remains strict. Watch exists to surface imperfect but plausible
    early-career applied-AI roles so the dashboard behaves like a useful daily
    cockpit instead of hiding every non-perfect candidate.
    """
    already_urls = {_job_url(job) for job in already_selected if _job_url(job)}
    already_ct_keys = {(str(job.get("company","")).strip().lower(), str(job.get("title","")).strip().lower())
                       for job in already_selected if job.get("company") and job.get("title")}

    from ranking.guardrails import location_verdict, DIRECT_ATS_SOURCES
    from resume.resume_profile import load_candidate_preferences

    pre_watch: list[dict] = []
    seen_urls: set[str] = set()
    seen_ct_keys: set[tuple[str, str]] = set()
    max_per_company = 3
    preferences = load_candidate_preferences()
    if max_age_days is None:
        from config import get_profile_config

        max_age_days = int(
            (get_profile_config().get("timeline") or {}).get("max_age_days", 7)
        )
    allowed_levels = set(preferences.get("target_levels", [])) | set(
        preferences.get("secondary_levels", [])
    )
    trusted_location_sources = DIRECT_ATS_SOURCES - {"ycombinator"}

    for raw in raw_jobs:
        url = _job_url(raw)
        if not url or url in already_urls or url in seen_urls:
            continue
        seen_urls.add(url)

        # Same-company+title dedup: catch same job from different API sources with different URLs
        company = str(raw.get("company", "")).strip().lower()
        title = str(raw.get("title", "")).strip().lower()
        c_t_key = (company, title)
        if company and title:
            if c_t_key in already_ct_keys or c_t_key in seen_ct_keys:
                continue
            seen_ct_keys.add(c_t_key)

        # Defense-in-depth geo gate: board/curated/API sources must pass the
        # strict location check. Direct-company ATS sources are trusted.
        if raw.get("source") not in trusted_location_sources:
            if not location_verdict(raw).get("allowed"):
                continue
        if _is_off_target_watch_title(raw):
            continue
        if not _within_timeline(raw, max_age_days):
            continue
        if not _plausible_ranking_candidate(raw, preferences):
            continue
        level = classify_target_level(raw.get("title", ""))
        if level not in allowed_levels:
            continue

        job = rank_job(dict(raw))
        if job.get("excluded") or _has_negated_ai_context(job):
            continue

        families = job.get("target_role_families") or classify_role_families(job)
        level = job.get("target_level") or level
        score = int(job.get("resume_match_score", 0) or 0)

        if not families:
            continue
        if level not in allowed_levels:
            continue
        verdict = job.get("location_verdict") or {}
        if verdict.get("status") != "us_verified":
            continue
        if score < WATCH_MIN_SCORE:
            continue

        apply_freshness_trust(job)
        job["dashboard_watch_reason"] = (
            "Near-match surfaced before strict Apply Now gate: "
            f"score={score}, level={level}, families={','.join(families)}"
        )
        if not job.get("why_risky"):
            job["why_risky"] = "Watch candidate: verify level, sponsorship, and role scope before applying."
        pre_watch.append(job)
        # Enrich a bounded reserve so excluded items can be replaced without
        # making the Watch path unbounded.
        if len(pre_watch) >= max(limit, limit * 3):
            break

    pre_watch.sort(key=lambda j: (
        {"A": 0, "B": 1, "C": 2}.get(j.get("priority", "C"), 3),
        freshness_sort_rank(j.get("freshness", "Unknown")),
        -j.get("resume_match_score", 0),
    ))

    # Watch is broader than Apply Now, but it must not bypass hard eligibility
    # blockers. Fetch employer descriptions in parallel before this final gate.
    enrich_candidates_before_eligibility(pre_watch)
    watch: list[dict] = []
    company_counts: dict[str, int] = {}
    for job in pre_watch:
        eligibility = evaluate_ready_to_apply(job)
        job["ready_to_apply"] = eligibility["ready_to_apply"]
        job["eligibility_severity"] = eligibility["severity"]
        job["eligibility_reason_codes"] = eligibility["reason_codes"]
        job["eligibility_reasons"] = eligibility["reasons"]
        if eligibility["severity"] == "excluded":
            continue

        company_key = str(job.get("company", "")).strip().lower()
        if company_key and company_counts.get(company_key, 0) >= max_per_company:
            continue
        watch.append(job)
        if company_key:
            company_counts[company_key] = company_counts.get(company_key, 0) + 1
        if len(watch) >= limit:
            break

    return watch


def _dashboard_job(job: dict, action_tag: str) -> dict:
    """Return a compact dashboard card payload for a scraped job."""
    from ranking.apply_window import annotate_apply_window

    base = dict(job)
    base["action_tag"] = base.get("action_tag") or action_tag
    base = annotate_apply_window(base)
    return {
        "company": base.get("company", ""),
        "title": base.get("title", base.get("role", "")),
        "location": base.get("location", ""),
        "resume_match_score": base.get("resume_match_score", base.get("score", 0)),
        "freshness": base.get("freshness", "Unknown"),
        "freshness_trust": base.get("freshness_trust", "unverified"),
        "posted_date": base.get("posted_date", ""),
        "freshness_source": base.get("freshness_source", ""),
        "source": base.get("source", ""),
        "ats_type": base.get("ats_type", ""),
        "apply_url": base.get("apply_url", base.get("raw_url", "")),
        "matched_keywords": base.get("matched_keywords", [])[:8],
        "missing_keywords": base.get("missing_keywords", [])[:8],
        "missing_skills": base.get("missing_skills", [])[:8],
        "target_role_families": base.get("target_role_families", base.get("role_families", [])),
        "why_matches": base.get("why_matches", ""),
        "why_risky": base.get("why_risky", ""),
        "application_angle": base.get("application_angle", ""),
        "reason_codes": base.get("eligibility_reason_codes", []),
        "reason_text": base.get("eligibility_reasons", []),
        "action_tag": base.get("action_tag", action_tag),
        "apply_window_score": base.get("apply_window_score", 0),
        "apply_window_label": base.get("apply_window_label", "medium"),
        "apply_window_reasons": base.get("apply_window_reasons", []),
        "apply_window_next_action": base.get("apply_window_next_action", "Review before applying"),
    }


def build_dashboard_jobs(
    ready_jobs: list[dict],
    needs_review_jobs: list[dict],
    excluded_jobs: list[dict],
    duplicate_jobs: list[dict],
    watch_jobs: list[dict] | None = None,
    limit_per_bucket: int = 10,
) -> list[dict]:
    """Build dashboard cards from scraper candidates.

    The local dashboard should not go empty just because strict Apply Now jobs
    are zero. It should still show Watch, Known Matches, and Skip reasons so the candidate
    can trust the system and review imperfect-but-real opportunities.
    """
    watch_bucket = (needs_review_jobs or []) + (watch_jobs or [])
    buckets = [
        ("apply_now", ready_jobs),
        ("watch", watch_bucket),
        ("known_match", duplicate_jobs),
        ("skip", excluded_jobs),
    ]
    payload: list[dict] = []
    for action_tag, jobs in buckets:
        for job in jobs[:limit_per_bucket]:
            payload.append(_dashboard_job(job, action_tag))
    return payload


def merge_pool_and_ranked_jobs(pool_jobs: list[dict], ranked_jobs: list[dict]) -> list[dict]:
    """Keep the broad pool while allowing stronger ranking buckets to upgrade rows."""
    merged: dict[tuple[str, str], dict] = {}
    for job in pool_jobs:
        key = (
            str(job.get("company") or "").strip().lower(),
            str(job.get("title") or job.get("role") or "").strip().lower(),
        )
        merged[key] = job
    for job in ranked_jobs:
        # Strict exclusions remain useful scoring metadata, but cannot remove a
        # minimal role+location acquisition match from the local pool.
        if job.get("action_tag") == "skip":
            continue
        key = (
            str(job.get("company") or "").strip().lower(),
            str(job.get("title") or job.get("role") or "").strip().lower(),
        )
        merged[key] = job
    return list(merged.values())


def scrape_all(
    max_selected: int = 15,
    dry_run: bool = True,
    max_workers: int = 8,
    run_window: str = "morning",
    source_group: str = "window",
) -> dict:
    """Run windowed sources in parallel, then merge, dedup, and rank.

    Args:
        max_selected: Max jobs to select after ranking.
        dry_run: If True, don't write to local SQLite.
        max_workers: Max concurrent threads for scraping.
        run_window: morning, afternoon, or evening query strategy.
        source_group: ``window`` follows the normal window plan; ``direct``
            runs every enabled direct ATS; ``board`` runs every enabled
            curated/board/API source while retaining the window's query text.

    Returns:
        dict with jobs, raw_count, source_results, failed_sources, etc.
    """
    approved_context = get_approved_profile_context()
    scrape_started = time.monotonic()
    _log_event("scrape_start", window=run_window, dry_run=dry_run, max_workers=max_workers)
    max_age_days = int(approved_context.compiled_config["timeline"]["max_age_days"])
    active_profile_id = approved_context.profile_id
    # Initialize discovery funnel
    funnel = new_funnel()
    def _record(stage: str, count: int, reason_codes: dict[str, int] | None = None, by_source: dict[str, int] | None = None) -> None:
        record_stage(
            funnel,
            stage,
            count,
            reason_codes=reason_codes,
            by_source=by_source,
        )

    result = {
        "jobs": [],
        "pool_jobs": [],
        "pool_count": 0,
        "raw_count": 0,
        "source_results": {},
        "failed_sources": [],
        "skipped_sources": [],
        "apify_runs": 0,
        "timings_seconds": {},
        "catalog": {"mode": "dry_run" if dry_run else "pending"},
        "discovery_funnel": funnel,
    }

    all_raw_jobs = []
    url_to_job = {}
    same_run_duplicates = 0

    from pipeline.query_strategy import normalize_window, source_enabled, source_plan_for_window
    global _ACTIVE_WINDOW
    _ACTIVE_WINDOW = normalize_window(run_window)
    if source_group not in {"window", "direct", "board"}:
        raise ValueError("source_group must be one of: window, direct, board")

    direct_sources = {"greenhouse", "lever", "ashby", "workable", "workday", "smartrecruiters"}

    def enabled_for_run(source_key: str) -> bool:
        if source_group == "window":
            return source_enabled(source_key, _ACTIVE_WINDOW)
        configured_somewhere = any(
            source_enabled(source_key, window)
            for window in ("morning", "afternoon", "evening")
        )
        if source_group == "direct":
            return source_key in direct_sources and configured_somewhere
        return source_key not in direct_sources and configured_somewhere

    registry = load_registry()
    companies = get_enabled_companies(registry)

    logger.info(
        "=== Parallel scrape: window=%s plan=%s companies=%d workers=%d ===",
        _ACTIVE_WINDOW,
        sorted(source_plan_for_window(_ACTIVE_WINDOW)),
        len(companies),
        max_workers,
    )

    # ── Build task list ──
    tasks = []

    # ATS-based companies (grouped by type)
    if enabled_for_run("greenhouse"):
        for company in get_companies_by_ats("greenhouse", registry):
            tasks.append(("greenhouse", company["company_name"], _scrape_greenhouse, company))
    if enabled_for_run("lever"):
        for company in get_companies_by_ats("lever", registry):
            tasks.append(("lever", company["company_name"], _scrape_lever, company))
    if enabled_for_run("ashby"):
        for company in get_companies_by_ats("ashby", registry):
            tasks.append(("ashby", company["company_name"], _scrape_ashby, company))
    if enabled_for_run("workable"):
        for company in get_companies_by_ats("workable", registry):
            tasks.append(("workable", company["company_name"], _scrape_workable, company))

    # Independent sources (no company needed)
    independent_tasks = [
        ("github_lists", "github_lists", _scrape_github_lists, None),
        ("ycombinator", "ycombinator", _scrape_ycombinator, None),
        ("builtin", "builtin", _scrape_builtin, None),
        ("wellfound", "wellfound", _scrape_wellfound, None),
        ("api_jsearch", "api_jsearch", _scrape_jsearch, None),
        ("api_adzuna", "api_adzuna", _scrape_adzuna, None),
        ("api_serpapi", "api_serpapi", _scrape_serpapi, None),
    ]
    tasks.extend(task for task in independent_tasks if enabled_for_run(task[0]))

    # Apify fallback (only if budget allows)
    if source_group == "window" and can_run_apify():
        unknown = get_unknown_ats_companies(registry)
        apify_candidates = [c for c in unknown if c.get("career_url")][:3]
        for company in apify_candidates:
            tasks.append(("apify", company["company_name"], _scrape_apify, company))
    else:
        logger.info("Apify budget exhausted for today")

    # Record tasks stage
    task_sources: dict[str, int] = {}
    for task in tasks:
        source_key = task[0]
        task_sources[source_key] = task_sources.get(source_key, 0) + 1
    _record("tasks", len(tasks), by_source=task_sources)

    # ── Execute all tasks in parallel ──
    logger.info("Launching %d tasks with %d workers (timeout=%ds)...",
                len(tasks), max_workers, _MAX_SCRAPE_SECONDS)

    source_started = time.monotonic()
    completed_tasks, timed_out, skipped = _execute_source_tasks(
        tasks,
        max_workers=max_workers,
        timeout_seconds=_MAX_SCRAPE_SECONDS,
    )
    result["failed_sources"].extend(timed_out)
    result["skipped_sources"].extend(skipped)
    result["timings_seconds"]["sources"] = round(time.monotonic() - source_started, 3)

    # Record requests stage (completed + failed + skipped)
    request_sources: dict[str, int] = {}
    for source_key, name, _ in completed_tasks:
        request_sources[source_key] = request_sources.get(source_key, 0) + 1
    for fail in timed_out:
        request_sources[fail["source"]] = request_sources.get(fail["source"], 0) + 1
    for skip in skipped:
        request_sources[skip["source"]] = request_sources.get(skip["source"], 0) + 1
    _record("requests", len(completed_tasks) + len(timed_out) + len(skipped), by_source=request_sources)

    if not dry_run:
        try:
            result["catalog"] = _persist_direct_source_snapshots(
                completed_tasks,
                run_window=_ACTIVE_WINDOW,
            )
            logger.info(
                "Catalog reconciled %d complete ATS sources (%d listings)",
                result["catalog"]["sources_reconciled"],
                result["catalog"]["listings_observed"],
            )
        except Exception as exc:
            result["catalog"] = {"mode": "error", "error": str(exc)}
            logger.exception("Direct-source catalog reconciliation failed")

    for source_key, name, scrape_result in completed_tasks:
        jobs = scrape_result.get("jobs", [])
        error = scrape_result.get("error")
        for job in jobs:
            raw_url = job.get("apply_url", job.get("raw_url", ""))
            sanitized_url = sanitize_url(raw_url)
            job["apply_url"] = sanitized_url
            job["raw_url"] = sanitized_url
            if not sanitized_url:
                continue
            if sanitized_url not in url_to_job:
                url_to_job[sanitized_url] = job
                all_raw_jobs.append(job)
            else:
                _merge_duplicate_job(url_to_job[sanitized_url], job)
                same_run_duplicates += 1

        result["source_results"][source_key] = result["source_results"].get(source_key, 0) + len(jobs)
        result["raw_count"] += scrape_result.get("raw_count", 0)
        if error:
            result["failed_sources"].append({"source": source_key, "company": name, "error": error})
        logger.info(
            "  %s %s: %d jobs%s",
            "FAILED" if error else "OK",
            source_key,
            len(jobs),
            f" (error: {error[:50]})" if error else "",
        )

    logger.info("Parallel scrape complete: %d raw jobs from %d sources",
                len(all_raw_jobs), len(result["source_results"]))

    # Record raw stage (after collecting all jobs from sources)
    raw_sources: dict[str, int] = {}
    for source_key, count in result["source_results"].items():
        raw_sources[source_key] = count
    _record("raw", len(all_raw_jobs), by_source=raw_sources)

    # Record normalized stage (after URL sanitization and dedup)
    normalized_sources: dict[str, int] = {}
    for job in all_raw_jobs:
        src = job.get("source", "unknown")
        normalized_sources[src] = normalized_sources.get(src, 0) + 1
    _record("normalized", len(all_raw_jobs), by_source=normalized_sources)

    # ── Strict geo gate for board/curated/API sources ──
    # Direct-company ATS jobs are trusted (curated U.S. firm list). Board sources
    # (YC, Simplify, Wellfound, JSearch, Adzuna, SerpApi) return globally and
    # must be hard-filtered before scoring so non-U.S. jobs never reach Watch.
    from ranking.guardrails import filter_jobs_by_location
    geo_before = len(all_raw_jobs)
    all_raw_jobs = filter_jobs_by_location(all_raw_jobs)
    geo_dropped = geo_before - len(all_raw_jobs)
    if geo_dropped:
        logger.info("Geo gate dropped %d non-U.S./ambiguous-location jobs", geo_dropped)

    # Record geo stage
    geo_sources: dict[str, int] = {}
    for job in all_raw_jobs:
        src = job.get("source", "unknown")
        geo_sources[src] = geo_sources.get(src, 0) + 1
    _record("location", len(all_raw_jobs), reason_codes={"dropped": geo_dropped}, by_source=geo_sources)

    # Minimal acquisition happens before strict ranking: configured role title
    # plus verified location only. Every matching row is retained locally so
    # browser filters and later resume scoring operate on a useful large pool.
    from pipeline.discovery_pool import build_discovery_pool

    pool_started = time.monotonic()
    pool_jobs = build_discovery_pool(all_raw_jobs)
    result["pool_jobs"] = pool_jobs
    result["pool_count"] = len(pool_jobs)
    result["timings_seconds"]["discovery_pool"] = round(
        time.monotonic() - pool_started, 3
    )
    logger.info(
        "Broad discovery pool: %d role+location matches from %d source rows",
        len(pool_jobs),
        len(all_raw_jobs),
    )

    # Record acquisition stage (configured role plus location preference).
    role_sources: dict[str, int] = {}
    for job in pool_jobs:
        src = job.get("source", "unknown")
        role_sources[src] = role_sources.get(src, 0) + 1
    _record(
        "acquisition",
        len(pool_jobs),
        reason_codes={"filtered": max(0, len(all_raw_jobs) - len(pool_jobs))},
        by_source=role_sources,
    )

    # ── ATS discovery for unknown companies ──
    unknown = get_unknown_ats_companies(registry)
    if source_group == "window" and unknown:
        logger.info("ATS discovery for %d unknown companies (up to 5)", len(unknown))
        try:
            from pipeline.ats_discovery import run_discovery
            discovery_results = run_discovery(max_companies=5)
            logger.info("Discovery: %d discovered, %d failed",
                        discovery_results["discovered"], discovery_results["failed"])
        except Exception as e:
            logger.warning("ATS discovery failed: %s", e)

    # ── Filter and rank ──
    logger.info("Filtering and ranking %d jobs...", len(all_raw_jobs))
    ranking_started = time.monotonic()
    ranked_jobs = filter_and_rank(all_raw_jobs)
    result["timings_seconds"]["initial_ranking"] = round(
        time.monotonic() - ranking_started, 3
    )
    logger.info("After ranking: %d jobs", len(ranked_jobs))

    # Record ranking stage
    ranking_sources: dict[str, int] = {}
    for job in ranked_jobs:
        src = job.get("source", "unknown")
        ranking_sources[src] = ranking_sources.get(src, 0) + 1
    _record("ranking", len(ranked_jobs), by_source=ranking_sources)

    # ── Freshness-prioritized selection ──
    # Historical jobs are deliberately re-ranked instead of discarded. The
    # incremental catalog owns deduplication and lifecycle state; this lets a
    # changed profile, scorer, or listing improve an existing recommendation.
    logger.info("Freshness and selection pipeline...")
    filtered_by_age_count = 0
    non_duplicate_jobs = []

    for job in ranked_jobs:
        # Timeline applies to every dashboard bucket, including known matches.
        if not _within_timeline(job, max_age_days):
            filtered_by_age_count += 1
            continue
        # Annotate freshness truth. Unknown source freshness becomes
        # "Newly Discovered" instead of pretending it is confirmed 0-24h.
        job = apply_freshness_trust(job)
        non_duplicate_jobs.append(job)

    logger.info("Filtered out %d jobs older than configured %d-day timeline", filtered_by_age_count, max_age_days)

    # Record freshness stage
    freshness_sources: dict[str, int] = {}
    freshness_reasons: dict[str, int] = {"too_old": filtered_by_age_count}
    for job in non_duplicate_jobs:
        src = job.get("source", "unknown")
        freshness_sources[src] = freshness_sources.get(src, 0) + 1
    _record("freshness", len(non_duplicate_jobs), reason_codes=freshness_reasons, by_source=freshness_sources)

    # Sort non-duplicates by Priority, trusted freshness, source confidence, then match score.
    non_duplicate_jobs.sort(key=lambda j: (
        {"A": 0, "B": 1, "C": 2}.get(j.get("priority", "C"), 3),
        freshness_sort_rank(j.get("freshness", "Unknown")),
        -j.get("source_quality_weight", 0),
        -j.get("resume_match_score", 0)
    ))

    candidate_pool_size = max(max_selected, max_selected * 3)

    # Truth before ranking: fetch employer-page descriptions for every
    # non-duplicate candidate before cutting to the Apply Now pool. Otherwise a
    # below-cutoff thin snippet can bypass the eligibility gate and later leak
    # into Watch as a plausible but disqualified role.
    enrichment_started = time.monotonic()
    try:
        enriched_count = enrich_candidates_before_eligibility(non_duplicate_jobs)
        if enriched_count:
            logger.info(
                "Description enrichment updated %d non-duplicate candidate fields",
                enriched_count,
            )
    except Exception as e:
        logger.warning("Candidate enrichment skipped: %s", e)
    result["timings_seconds"]["candidate_enrichment"] = round(
        time.monotonic() - enrichment_started, 3
    )

    # Re-rank enriched jobs (refreshes skill/eligibility-relevant metadata)
    from ranking.score import rank_job

    for job in non_duplicate_jobs:
        try:
            rank_job(job)
            apply_freshness_trust(job)
        except Exception:
            pass

    non_duplicate_jobs.sort(key=lambda j: (
        {"A": 0, "B": 1, "C": 2}.get(j.get("priority", "C"), 3),
        freshness_sort_rank(j.get("freshness", "Unknown")),
        -j.get("source_quality_weight", 0),
        -j.get("resume_match_score", 0),
    ))
    candidate_pool = non_duplicate_jobs[:candidate_pool_size]

    # --- Skill & temporal scoring ---
    from core.skill_extractor import extract_skills
    from core.skill_matcher import skill_match, load_user_profile
    from core.temporal_scorer import combined_weight
    user_profile = load_user_profile()
    for job in candidate_pool:
        # extract skills from full_text (fallback to description)
        text = job.get("full_text", "") or job.get("description", "")
        job_skills = set(extract_skills(text))
        match_score, missing = skill_match(text, user_profile)
        job["extracted_skills"] = sorted(job_skills)
        job["skill_match"] = round(match_score, 2)
        job["missing_skills"] = missing
        # temporal weight using freshness field (already set by apply_freshness_trust)
        fresh = job.get("freshness", "Unknown")
        job["time_weight"] = round(combined_weight(fresh), 2)
        job["overall_score"] = round(job["skill_match"] * job["time_weight"], 2)

    # Apply ready-to-apply gate after enrichment so current-enrollment/security
    # restrictions found in full descriptions can prevent dashboard noise.
    ready_jobs, needs_review_jobs, eligibility_excluded = filter_ready_to_apply_jobs(candidate_pool)
    logger.info(
        "Ready-to-apply eligibility: %d ready, %d needs review, %d excluded",
        len(ready_jobs), len(needs_review_jobs), len(eligibility_excluded),
    )
    for job in (needs_review_jobs + eligibility_excluded)[:20]:
        logger.info(
            "ELIGIBILITY %s: %s — %s reasons=%s",
            job.get("eligibility_severity", "unknown").upper(),
            job.get("title", ""),
            job.get("company", ""),
            ",".join(job.get("eligibility_reason_codes", [])),
        )
    selected = ready_jobs[:max_selected]

    watch_started = time.monotonic()
    watch_candidates = build_watch_candidates(
        raw_jobs=all_raw_jobs,
        already_selected=ready_jobs + needs_review_jobs + eligibility_excluded,
        limit=max_selected * 4,
        max_age_days=max_age_days,
    )
    fresh_watch_candidates = watch_candidates[:max_selected]
    logger.info(
        "Dashboard Watch surfacing: %d fresh near-matches from %d broad candidates",
        len(fresh_watch_candidates),
        len(watch_candidates),
    )
    result["timings_seconds"]["watch_build"] = round(
        time.monotonic() - watch_started, 3
    )

    result["jobs"] = selected
    ranked_dashboard_jobs = build_dashboard_jobs(
        ready_jobs=ready_jobs,
        needs_review_jobs=needs_review_jobs,
        excluded_jobs=eligibility_excluded,
        duplicate_jobs=[],
        watch_jobs=fresh_watch_candidates,
        limit_per_bucket=max_selected,
    )
    result["dashboard_jobs"] = merge_pool_and_ranked_jobs(
        pool_jobs,
        ranked_dashboard_jobs,
    )
    # Tag each dashboard job with the active profile id before it reaches the DB.
    if active_profile_id:
        from ranking.guardrails import detect_visa_sponsorship  # noqa: PLC0415

        for _dj in result["dashboard_jobs"]:
            _dj["profile_id"] = active_profile_id
            if "visa_sponsorship" not in _dj:
                _dj["visa_sponsorship"] = detect_visa_sponsorship(_dj)
    result["dup_count"] = same_run_duplicates
    result["dashboard_watch_candidates"] = fresh_watch_candidates
    result["dashboard_watch_count"] = len(fresh_watch_candidates)
    result["eligibility_needs_review"] = needs_review_jobs
    result["eligibility_needs_review_count"] = len(needs_review_jobs)
    result["eligibility_excluded"] = eligibility_excluded
    result["eligibility_excluded_count"] = len(eligibility_excluded)
    result["timings_seconds"]["total"] = round(time.monotonic() - scrape_started, 3)

    # Record link stage (jobs with verified links)
    link_sources: dict[str, int] = {}
    link_reasons: dict[str, int] = {}
    for job in result["dashboard_jobs"]:
        src = job.get("source", "unknown")
        link_sources[src] = link_sources.get(src, 0) + 1
        link_status = job.get("link_status", "unknown")
        link_reasons[link_status] = link_reasons.get(link_status, 0) + 1
    _record("link", len(result["dashboard_jobs"]), reason_codes=link_reasons, by_source=link_sources)

    # Record lifecycle stage (listing_state breakdown)
    lifecycle_sources: dict[str, int] = {}
    lifecycle_reasons: dict[str, int] = {}
    for job in result["dashboard_jobs"]:
        src = job.get("source", "unknown")
        lifecycle_sources[src] = lifecycle_sources.get(src, 0) + 1
        state = job.get("listing_state", "active")
        lifecycle_reasons[state] = lifecycle_reasons.get(state, 0) + 1
    _record("lifecycle", len(result["dashboard_jobs"]), reason_codes=lifecycle_reasons, by_source=lifecycle_sources)

    # Record buckets stage (action_tag breakdown)
    buckets_sources: dict[str, int] = {}
    buckets_reasons: dict[str, int] = {}
    for job in result["dashboard_jobs"]:
        src = job.get("source", "unknown")
        buckets_sources[src] = buckets_sources.get(src, 0) + 1
        bucket = job.get("action_tag", "watch")
        buckets_reasons[bucket] = buckets_reasons.get(bucket, 0) + 1
    _record("buckets", len(result["dashboard_jobs"]), reason_codes=buckets_reasons, by_source=buckets_sources)

    # Record persistence stage (jobs that will be persisted)
    persistence_sources: dict[str, int] = {}
    for job in result["dashboard_jobs"]:
        src = job.get("source", "unknown")
        persistence_sources[src] = persistence_sources.get(src, 0) + 1
    _record("persistence", len(result["dashboard_jobs"]), by_source=persistence_sources)

    # Record dashboard stage
    dashboard_sources: dict[str, int] = {}
    for job in result["dashboard_jobs"]:
        src = job.get("source", "unknown")
        dashboard_sources[src] = dashboard_sources.get(src, 0) + 1
    _record("dashboard", len(result["dashboard_jobs"]), by_source=dashboard_sources)

    # Attach funnel to result for API exposure
    result["discovery_funnel"] = funnel
    if not dry_run:
        try:
            from core.source_quality import record_result

            result["source_quality_path"] = str(record_result(result))
        except Exception as exc:
            logger.warning("Could not retain source-quality report: %s", exc)

    freshness_counts = {}
    for j in selected:
        f = j.get("freshness", "Unknown")
        freshness_counts[f] = freshness_counts.get(f, 0) + 1
    logger.info("Selected freshness: %s", freshness_counts)
    logger.info("=== Done: %d selected, %d same-run dups, %d raw ===",
                len(selected), same_run_duplicates, len(all_raw_jobs))
    _log_event("scrape_complete", window=run_window, dry_run=dry_run,
               selected=len(selected), dups=same_run_duplicates, raw=len(all_raw_jobs),
               failed=len(result["failed_sources"]))

    return result
