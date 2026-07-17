"""
ranking/guardrails.py — Quality guardrails for job selection.

These helpers keep the pipeline aligned to the goal:
right time, right job, right skill, with truthful freshness and safe filtering.
"""
from __future__ import annotations

import re


CONFIRMED_FRESHNESS_VALUES = {
    "New (0-24h)",
    "Recent (24-48h)",
    "This Week (3-7d)",
    "Old (8-14d)",
    "Stale (15d+)",
    "Older (30d+)",
}

DIRECT_ATS_SOURCES = {
    "greenhouse",
    "ashby",
    "lever",
    "workable",
    "workday",
    "smartrecruiters",
}

CURATED_REPOST_SOURCES = {"github_list", "github_lists"}
BROAD_API_SOURCES = {"api_jsearch", "api_adzuna", "api_serpapi", "jsearch", "adzuna", "serpapi"}


# Patterns that explicitly state a posting offers visa sponsorship.
_VISA_SPONSORSHIP_SUPPORT = (
    r"\b(?:visa\s+)?sponsorship\s+(?:is\s+)?(?:available|provided|supported|offered)\b",
    r"\b(?:stem\s+)?opt\s+sponsorship\s+(?:is\s+)?(?:available|provided|supported|offered)\b",
    r"\bf-?1(?:\s+opt)?\s+sponsorship\s+(?:is\s+)?(?:available|provided|supported|offered)\b",
    r"\bwe\s+(?:do\s+)?sponsor\s+(?:f-?1|opt|international)\s+(?:candidates|applicants|employees)\b",
    r"\bwe\s+(?:do\s+)?sponsor\s+(?:h-?1b|f-?1|opt|cpt)(?:\s+visas?)?\b",
)


def detect_visa_sponsorship(job: dict) -> int:
    """Return 1 if the job text explicitly offers visa sponsorship, else 0.

    This is a conservative signal: only explicit support text counts. A missing
    value (no text scanned yet) is reported as -1 by the DB default, not 0,
    so the UI can distinguish "no" from "unknown".
    """
    text = " ".join(
        str(job.get(key) or "")
        for key in ("title", "description", "full_text", "why_matches")
    ).lower()
    if not text.strip():
        return 0
    # Reject explicit *non*-support phrasing before the support check.
    _VISA_NO_SUPPORT = (
        "no sponsorship",
        "not sponsor",
        "do not sponsor",
        "does not sponsor",
        "cannot sponsor",
        "sponsorship not",
        "no h-1",
        "no h1",
        "no opt",
        "no cpt",
    )
    if any(neg in text for neg in _VISA_NO_SUPPORT):
        return 0
    for pattern in _VISA_SPONSORSHIP_SUPPORT:
        if re.search(pattern, text):
            return 1
    return 0


def apply_freshness_trust(job: dict) -> dict:
    """Annotate freshness truth.

    Unknown freshness must not be silently converted into confirmed "New".
    We mark those as "Newly Discovered" so the candidate knows the system found them today,
    not that the employer posted them today.
    """
    freshness = job.get("freshness") or "Unknown"
    source = job.get("source", "")

    if freshness in CONFIRMED_FRESHNESS_VALUES:
        job["freshness_trust"] = "confirmed_posted_date"
        job["confirmed_posted_date"] = True
        return job

    if freshness == "Newly Discovered":
        job["freshness_trust"] = "discovered_not_posted"
        job["confirmed_posted_date"] = False
        job.setdefault("freshness_note", "Found by the system today; original posting date was not available from source.")
        return job

    if freshness == "Unknown":
        job["freshness"] = "Newly Discovered"
        job["freshness_trust"] = "discovered_not_posted"
        job["confirmed_posted_date"] = False
        job["freshness_note"] = "Found by the system today; original posting date was not available from source."
        if source in DIRECT_ATS_SOURCES:
            job["source_quality_note"] = "Direct company ATS, but posting date unavailable."
        # If enrichment recovered an explicit posted_date from the employer
        # page, upgrade the trust flag so the UI can show it as confirmed.
        if job.get("posted_date"):
            job["freshness_trust"] = "confirmed_posted_date"
            job["confirmed_posted_date"] = True
        return job

    job["freshness_trust"] = "unverified"
    job["confirmed_posted_date"] = False
    return job


def is_us_location_allowed(location: str) -> bool:
    """Return True only for U.S., Remote U.S., or unknown locations.

    Unknown locations stay allowed because some ATS feeds omit location; they are
    handled by score/notes rather than hard-excluded.
    """
    loc = (location or "").strip().lower()
    if not loc:
        return True

    remote_us_signals = [
        "remote in usa", "remote in us", "remote us", "remote usa",
        "remote - us", "remote - usa", "remote — us", "remote — usa",
        "united states", "u.s.", "usa",
    ]
    if any(sig in loc for sig in remote_us_signals):
        return True

    non_us_patterns = [
        r"\bcanada\b", r"\bon\b", r"\btoronto\b", r"\bvancouver\b", r"\bkitchener\b", r"\bwaterloo\b",
        r"\blondon\b", r"\buk\b", r"\bunited kingdom\b", r"\beurope\b", r"\beu\b",
        r"\bbelgrade\b", r"\bberlin\b", r"\bparis\b", r"\bamsterdam\b", r"\bdublin\b",
        r"\bsingapore\b", r"\btokyo\b", r"\bsydney\b", r"\bmelbourne\b",
        r"\bindia\b", r"\bbangalore\b", r"\bhyderabad\b",
    ]
    if any(re.search(p, loc) for p in non_us_patterns):
        return False

    us_state_patterns = [
        " al", " ak", " az", " ar", " ca", " co", " ct", " dc", " de", " fl", " ga", " hi",
        " ia", " id", " il", " in", " ks", " ky", " la", " ma", " md", " me", " mi", " mn",
        " mo", " ms", " mt", " nc", " nd", " ne", " nh", " nj", " nm", " nv", " ny", " oh",
        " ok", " or", " pa", " ri", " sc", " sd", " tn", " tx", " ut", " va", " vt", " wa",
        " wi", " wv", " wy",
    ]
    normalized = " " + re.sub(r"[^a-z]", " ", loc) + " "
    if any(state in normalized for state in us_state_patterns):
        return True

    # Plain city-only locations are ambiguous. Keep them only if they don't carry
    # a known non-US signal.
    return True


# Pipeline-level strict geo gate.
#
# `is_us_location_allowed()` is a scoring adjuster and intentionally allows
# ambiguous/empty locations. `allow_job_location()` is STRICTER: it exists to
# hard-drop non-U.S. jobs before they enter scoring / Watch / Apply buckets.
# Board adapters (YC, Simplify, Wellfound, JSearch) return globally, so this
# gate must not rely on scoring bonuses to suppress non-U.S. results.
NON_US_TERMS = {
    "canada", "toronto", "vancouver", "kitchener", "waterloo", "montreal", "ottowa",
    "calgary", "edmonton",
    "london", "uk", "united kingdom", "britain", "europe", "eu", "berlin", "paris",
    "amsterdam", "dublin", "munich", "zurich", "barcelona", "madrid", "lisbon",
    "belgrade", "warsaw", "prague", "stockholm", "oslo", "copenhagen",
    "india", "bangalore", "hyderabad", "mumbai", "delhi", "chennai", "pune", "kolkata",
    "singapore", "tokyo", "japan", "australia", "sydney", "melbourne", "perth",
    "new zealand", "remote, australia", "remote, india", "remote, uk", "remote, europe",
    "remote/onsite",
}
US_REMOTE_SIGNALS = {
    "remote in usa", "remote in us", "remote us", "remote usa",
    "remote - us", "remote - usa", "remote — us", "remote — usa",
    "united states", "u.s.", "usa",
}


def allow_job_location(location: str | None) -> bool:
    """Strict gate: True only for U.S., Remote-U.S., or plausibly-U.S. locations.

    Ambiguous locations without a clear U.S./Remote-U.S. signal are rejected
    because board adapters return global results and we cannot tell.
    """
    loc = (location or "").strip().lower()
    if not loc:
        return False

    # Explicit US remote signals → keep immediately.
    if any(sig in loc for sig in US_REMOTE_SIGNALS):
        return True

    # Explicit US state signals → keep even if mixed with ambiguous tokens
    # like "Remote / Onsite" (YC adapter sets this).
    #
    # Tokenize on commas first so "Kitchener, ON, Canada" → ["kitchener", "on", "canada"]
    # and "New York, NY" → ["new york", "ny"]. Then match tokens with a proper
    # lookup set. This prevents ", ca" from falsely matching "on, canada".
    def _tokenize_location(s: str) -> list[str]:
        parts = re.split(r"[,/]", s)
        tokens: list[str] = []
        for part in parts:
            cleaned = re.sub(r"[^a-z ]", " ", part.lower()).strip()
            for tok in re.split(r"\s+", cleaned):
                if tok and len(tok) >= 2:
                    tokens.append(tok)
        return tokens

    us_state_tokens = {
        "al","ak","az","ar","ca","co","ct","dc","de","fl","ga","hi","ia","id","il",
        "in","ks","ky","la","ma","md","me","mi","mn","mo","ms","mt","nc","nd","ne",
        "nh","nj","nm","nv","ny","oh","ok","or","pa","ri","sc","sd","tn","tx","ut",
        "va","vt","wa","wi","wv","wy",
    }
    loc_tokens = _tokenize_location(loc)
    if any(tok in us_state_tokens for tok in loc_tokens):
        return True

    us_city_tokens = {
        "york", "francisco", "seattle", "austin", "denver", "boston", "chicago",
        "angeles", "atlanta", "portland", "miami", "dallas", "houston", "detroit",
        "minneapolis", "philadelphia", "phoenix", "diego", "jose", "oakland",
        "sacramento", "pittsburgh", "raleigh", "nashville", "boulder",
    }
    if any(tok in us_city_tokens for tok in loc_tokens):
        return True

    # Now reject known non-US terms.
    if any(term in loc for term in NON_US_TERMS):
        return False

    # Ambiguous/city-only without a US signal → hard reject at pipeline level.
    return False


def location_verdict(job: dict) -> dict:
    """Return strict location confidence for a job.

    This is stricter than `is_us_location_allowed()`: dashboard candidates must
    prove U.S./Remote-U.S. location unless they are a direct ATS row that still
    needs enrichment. Direct ATS rows with blank location are allowed to proceed
    only with a score cap; they should not become Apply Now until enriched.
    """
    source = str(job.get("source") or "").lower()
    location = job.get("location")
    loc = (location or "").strip().lower()
    trusted_location_sources = DIRECT_ATS_SOURCES - {"ycombinator"}
    from config import get_profile_config

    preferred_locations = [
        str(value).strip().lower()
        for value in get_profile_config().get("locations", [])
        if str(value).strip()
    ]
    uses_us_policy = not preferred_locations or any(
        value in {"us", "u.s.", "usa", "united state", "united states", "remote us", "remote usa"}
        or value.startswith("united state")
        for value in preferred_locations
    )

    if not loc:
        if source in trusted_location_sources:
            return {
                "allowed": True,
                "status": "trusted_company_unknown",
                "reason": "Direct ATS source but location missing; enrich before Apply Now.",
                "score_cap": 65,
            }
        return {
            "allowed": False,
            "status": "missing",
            "reason": "Location missing from untrusted board/API source.",
            "score_cap": 40,
        }

    if not uses_us_policy:
        for preferred in preferred_locations:
            if preferred == "remote" and "remote" in loc:
                return {"allowed": True, "status": "configured_verified", "reason": "Configured remote location matched.", "score_cap": None}
            if preferred in loc or loc in preferred:
                return {"allowed": True, "status": "configured_verified", "reason": "Configured location matched.", "score_cap": None}
        return {"allowed": False, "status": "outside_configured_locations", "reason": "Location does not match configured preferences.", "score_cap": 40}

    if any(sig in loc for sig in US_REMOTE_SIGNALS):
        return {"allowed": True, "status": "us_verified", "reason": "Remote/U.S. signal present.", "score_cap": None}

    # Reject non-U.S. before checking city tokens so explicit global locations
    # like "Remote / Berlin" cannot pass through as ambiguous.
    if any(term in loc for term in NON_US_TERMS):
        return {"allowed": False, "status": "non_us", "reason": "Non-U.S. location signal present.", "score_cap": 40}

    if allow_job_location(loc):
        return {"allowed": True, "status": "us_verified", "reason": "U.S. city/state signal present.", "score_cap": None}

    return {"allowed": False, "status": "ambiguous", "reason": "No clear U.S./Remote-U.S. signal.", "score_cap": 40}


def filter_jobs_by_location(jobs: list[dict]) -> list[dict]:
    """Return only jobs that survive the strict geo gate.

    Board/curated/API sources with blank/ambiguous/non-U.S. locations are hard
    dropped. Direct-company ATS rows with missing location are retained only so
    enrichment can try to recover location; scoring caps prevent Apply Now.
    """
    out = []
    for j in jobs:
        verdict = location_verdict(j)
        j["location_verdict"] = verdict
        if verdict["allowed"]:
            out.append(j)
    return out


def is_research_engineering_role(title: str, description: str = "") -> bool:
    """Allow research-titled jobs only when engineering/product work is explicit."""
    text = f"{title or ''} {description or ''}".lower()
    title_lower = (title or "").lower()

    research_title = bool(re.search(r"\b(researcher|research\s+(intern|co-op|coop|fellow|assistant|scientist))\b", title_lower))
    if not research_title:
        return True

    hard_research_signals = [
        "publication", "published", "peer-reviewed", "top-tier conference",
        "research agenda", "novel algorithm", "theoretical", "phd required",
        "ph.d. required", "postdoctoral", "academic lab",
    ]
    if any(sig in text for sig in hard_research_signals):
        return False

    engineering_signals = [
        "production", "deploy", "deployment", "pipeline", "data engineering",
        "backend", "api", "fastapi", "service", "platform", "customer",
        "product", "monitoring", "observability", "mlops", "docker",
        "ci/cd", "evaluation system", "automation",
    ]
    signal_count = sum(1 for sig in engineering_signals if sig in text)
    return signal_count >= 2


def source_quality_weight(source: str) -> int:
    """Higher is better. Used as a tie-breaker after role/relevance filters."""
    s = (source or "").lower()
    if s in DIRECT_ATS_SOURCES:
        return 30
    if s in CURATED_REPOST_SOURCES:
        return 20
    if s in BROAD_API_SOURCES:
        return 10
    if s.startswith("api_"):
        return 10
    return 15


def freshness_sort_rank(freshness: str) -> int:
    """Lower rank sorts earlier."""
    return {
        "New (0-24h)": 0,
        "Recent (24-48h)": 1,
        "Newly Discovered": 2,
        "This Week (3-7d)": 3,
        "Old (8-14d)": 4,
        "Stale (15d+)": 5,
        "Unknown": 6,
    }.get(freshness or "Unknown", 6)
