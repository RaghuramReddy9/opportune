"""Load generic fallback profile files and overlay the active approved profile."""
import re
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set

import yaml

from config import PROJECT_ROOT, TRACKER_DIR

logger = logging.getLogger("resume_profile")

# Older local file profiles remain readable as a fallback. An active approved
# SQLite profile takes precedence through get_profile_config().
_PROFILE_PATH = TRACKER_DIR / "resume" / "resume_profile.md"
_PROJECT_PROFILE_TEMPLATE = PROJECT_ROOT / "resume" / "resume_profile.md"
_INSTALLED_PROFILE_TEMPLATE = Path(sys.prefix) / "resume" / "resume_profile.md"
_PROFILE_TEMPLATE_PATH = _PROJECT_PROFILE_TEMPLATE if _PROJECT_PROFILE_TEMPLATE.exists() else _INSTALLED_PROFILE_TEMPLATE
_CANDIDATE_PROFILE_PATH = TRACKER_DIR / "candidate_profile.yaml"
_PROJECT_CANDIDATE_TEMPLATE = PROJECT_ROOT / "candidate_profile.yaml"
_INSTALLED_CANDIDATE_TEMPLATE = Path(sys.prefix) / "candidate_profile.yaml"
_CANDIDATE_TEMPLATE_PATH = _PROJECT_CANDIDATE_TEMPLATE if _PROJECT_CANDIDATE_TEMPLATE.exists() else _INSTALLED_CANDIDATE_TEMPLATE

# ── Parsed profile data (loaded once) ──
_profile = None
_candidate_preferences = None


def load_profile() -> dict:
    """Load and parse resume_profile.md into a structured dict."""
    global _profile
    if _profile is not None:
        return _profile

    profile_path = _PROFILE_PATH if _PROFILE_PATH.exists() else _PROFILE_TEMPLATE_PATH
    if not profile_path.exists():
        logger.warning("resume_profile.md not found at %s", profile_path)
        return _empty_profile()

    text = profile_path.read_text()
    _profile = _parse_profile(text)
    logger.info("Resume profile loaded: %d skills, %d projects, %d keywords",
                len(_profile["all_skills"]), len(_profile["projects"]),
                len(_profile["strong_keywords"]))
    return _profile


def _empty_profile() -> dict:
    return {
        "all_skills": set(),
        "strong_keywords": set(),
        "projects": {},
        "project_names": [],
        "role_targets": {"high": set(), "medium": set(), "low": set()},
        "exclusion_patterns": [],
        "opt_friendly_signals": set(),
        "opt_risk_patterns": [],
        "enrollment_risk_patterns": [],
        "search_queries": [],
        "raw_text": "",
    }


def _default_candidate_preferences() -> dict:
    return {
        "education_status": "unknown",
        "target_levels": ["entry_level", "junior", "new_grad", "associate", "engineer_i", "zero_to_two_years", "early_career"],
        "secondary_levels": [],
        "internship_policy": "explicit_graduate_eligibility_required",
        "visa_status": {"needs_sponsorship_future": True, "opt_eligible": True},
        "location_policy": {"country": "US", "remote_us_ok": True},
    }


def validate_candidate_preferences(prefs: dict) -> List[str]:
    """Return validation errors for candidate_profile.yaml preferences."""
    errors = []
    allowed_levels = {"internship", "co_op", "new_grad", "entry_level", "junior", "associate", "engineer_i", "zero_to_two_years", "early_career", "mid_level"}
    target_levels = set(prefs.get("target_levels", []))
    secondary_levels = set(prefs.get("secondary_levels", []))
    unknown = (target_levels | secondary_levels) - allowed_levels
    if unknown:
        errors.append("Unknown target levels: {}".format(", ".join(sorted(unknown))))
    if not target_levels:
        errors.append("At least one target level is required")
    return errors


def load_candidate_preferences() -> dict:
    """Load candidate-specific search preferences from candidate_profile.yaml.

    This makes the project reusable: users can upload/change a resume and set
    their target levels without editing ranking code.
    """
    global _candidate_preferences
    if _candidate_preferences is not None:
        return _candidate_preferences

    merged = _default_candidate_preferences()
    for pref_path in (_CANDIDATE_PROFILE_PATH, _CANDIDATE_TEMPLATE_PATH):
        if pref_path.exists():
            data = yaml.safe_load(pref_path.read_text()) or {}
            candidate = data.get("candidate", {})
            merged.update(candidate)
            break

    # config.yaml is the public user-facing source of truth. The candidate
    # profile remains a compatibility fallback for fields not exposed in UI.
    from config import get_profile_config

    profile = get_profile_config()
    if profile.get("target_levels"):
        merged["target_levels"] = list(profile["target_levels"])
    if profile.get("locations"):
        merged["preferred_locations"] = list(profile["locations"])
    visa_policy = profile.get("visa_policy")
    if visa_policy:
        merged["visa_policy"] = visa_policy
        merged["visa_status"] = {
            "needs_sponsorship_future": visa_policy in {"needs_sponsorship", "opt_cpt", "custom"},
            "opt_eligible": visa_policy == "opt_cpt",
        }
    timeline = profile.get("timeline") or {}
    if timeline.get("max_age_days"):
        merged["timeline"] = {"max_age_days": int(timeline["max_age_days"])}

    errors = validate_candidate_preferences(merged)
    if errors:
        raise ValueError("Invalid candidate_profile.yaml: " + "; ".join(errors))

    _candidate_preferences = merged
    return _candidate_preferences


def _parse_profile(text: str) -> dict:
    """Parse the markdown resume profile into structured data."""
    profile = _empty_profile()
    profile["raw_text"] = text.lower()

    # ── Extract skills from all sections ──
    skills_section = _extract_section(text, "Core Skills", "Professional Experience")
    if skills_section:
        profile["all_skills"] = _extract_bullets_and_text(skills_section)

    # ── Extract strong keywords ──
    kw_section = _extract_section(text, "Matching Keywords", "Strict Exclusion Rules")
    if not kw_section:
        kw_section = _extract_section(text, "Strong Resume Match Keywords", "Source Strategy")
    if kw_section:
        profile["strong_keywords"] = _extract_bullets(kw_section)

    # ── Extract projects ──
    profile["projects"] = _extract_projects(text)
    profile["project_names"] = list(profile["projects"].keys())

    # ── Extract role targets ──
    high_section = _extract_section(text, "Highest Priority", "Medium Priority")
    if not high_section:
        high_section = _extract_section(text, "Highest priority roles", "Medium priority roles")
    if high_section:
        profile["role_targets"]["high"] = _extract_bullets(high_section)

    med_section = _extract_section(text, "Medium priority roles", "Lower priority roles")
    if med_section:
        profile["role_targets"]["medium"] = _extract_bullets(med_section)

    low_section = _extract_section(text, "Lower priority roles", "Matching Keywords")
    if low_section:
        profile["role_targets"]["low"] = _extract_bullets(low_section)

    # ── Extract exclusion patterns ──
    excl_section = _extract_section(text, "Strict Exclusion Rules", "OPT-Friendly Search Rules")
    if excl_section:
        profile["exclusion_patterns"] = _extract_bullets(excl_section)

    # ── Extract OPT-friendly signals ──
    opt_section = _extract_section(text, "OPT-Friendly Search Rules", "Priority Scoring")
    if opt_section:
        boost = _extract_section(opt_section, "Boost roles if they mention", "mark opt/visa risk = high if")
        if boost:
            profile["opt_friendly_signals"] = _extract_bullets(boost)
        risk = _extract_section(opt_section, "mark opt/visa risk = high if", None)
        if risk:
            profile["opt_risk_patterns"] = _extract_bullets(risk)

    # ── Extract enrollment risk patterns ──
    enroll = _extract_section(text, "Enrollment Risk", None)
    if enroll:
        profile["enrollment_risk_patterns"] = _extract_bullets(enroll)

    # ── Extract search queries ──
    query_section = _extract_section(text, "Search Queries", "ATS X-ray queries")
    if query_section:
        profile["search_queries"] = _extract_bullets(query_section)

    return profile


def _extract_section(text: str, start_marker: str, end_marker: str = None) -> str:
    """Extract text between two markers case-insensitively."""
    start = text.lower().find(start_marker.lower())
    if start == -1:
        return ""
    # Do not skip the first line; the bullet/comma parser will strip any prefixes
    if end_marker:
        end = text.lower().find(end_marker.lower(), start)
        if end == -1:
            end = len(text)
    else:
        end = len(text)
    return text[start:end]


def _extract_bullets(text: str) -> set:
    """Extract bullet points from markdown text. Also handles comma-separated lists."""
    items = set()
    prefix_pattern = r'^(boost roles (mentioning|if they mention)|exclude roles that clearly say|mark opt/visa risk\s*=\s*high if):\s*'
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            item = line[2:].strip().lower()
            item = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', item)
            item = re.sub(prefix_pattern, '', item).strip()
            if item:
                items.add(item)
        elif line and not line.startswith("#") and not line.startswith("["):
            # Handle comma-separated lists on a single line
            # Skip lines that are just headers or empty
            if ":" in line and not any(c.isalpha() for c in line.split(":")[1][:20].replace(",", "").replace(" ", "")):
                continue
            for part in re.split(r'[,;]', line):
                part = part.strip().lower()
                # Remove leading "boost roles mentioning:" type prefixes
                part = re.sub(prefix_pattern, '', part).strip()
                part = re.sub(r'^[^a-z0-9]+', '', part).strip()
                if part and len(part) > 1:
                    items.add(part)
    return items


def _extract_bullets_and_text(text: str) -> set:
    """Extract both bullet points and comma/semicolon-separated items."""
    items = set()
    prefix_pattern = r'^(boost roles (mentioning|if they mention)|exclude roles that clearly say|mark opt/visa risk\s*=\s*high if):\s*'
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            content = line[2:].strip().lower()
            # Split on commas, semicolons, "and", "or"
            for part in re.split(r'[,;/]|\band\b|\bor\b', content):
                part = part.strip()
                part = re.sub(prefix_pattern, '', part).strip()
                if part and len(part) > 1:
                    items.add(part)
        elif line and not line.startswith("#"):
            # Also grab inline text
            for part in re.split(r'[,;/]', line):
                part = part.strip().lower()
                part = re.sub(prefix_pattern, '', part).strip()
                if part and len(part) > 1:
                    items.add(part)
    return items


def _extract_projects(text: str) -> dict:
    """Extract project names, technologies, and highlights."""
    projects = {}
    # Find all ### level project headers
    project_blocks = re.findall(r'###\s+(.+?)\n(.*?)(?=###|\Z)', text, re.DOTALL)
    for name, content in project_blocks:
        name = name.strip()
        if "project" in name.lower() or any(kw in name.lower() for kw in
            [
                "assistant", "intelligence", "operations", "research",
                "medassist", "qa", "document", "inspector", "pipeline",
                "rag", "agent", "deal flow", "platform", "retrieval",
            ]):
            tech_section = _extract_section(content, "Technologies:", "Highlights:")
            highlights_section = _extract_section(content, "Highlights:", "Best matching roles:")
            roles_section = _extract_section(content, "Best matching roles:", None)

            technologies = _extract_bullets_and_text(tech_section) if tech_section else set()
            highlights = _extract_bullets(highlights_section) if highlights_section else set()
            best_roles = _extract_bullets(roles_section) if roles_section else set()

            projects[name.lower()] = {
                "name": name,
                "technologies": technologies,
                "highlights": highlights,
                "best_roles": best_roles,
                "full_text": content.lower(),
            }
    return projects


# ── Public accessors ──

def get_all_skills() -> Set[str]:
    return load_profile()["all_skills"]


def get_strong_keywords() -> Set[str]:
    return load_profile()["strong_keywords"]


def get_projects() -> Dict:
    return load_profile()["projects"]


def get_project_names() -> List[str]:
    return load_profile()["project_names"]


def get_role_targets() -> Dict[str, Set[str]]:
    return load_profile()["role_targets"]


def get_exclusion_patterns() -> List[str]:
    return load_profile()["exclusion_patterns"]


def get_opt_friendly_signals() -> Set[str]:
    return load_profile()["opt_friendly_signals"]


def get_opt_risk_patterns() -> List[str]:
    return load_profile()["opt_risk_patterns"]


def get_enrollment_risk_patterns() -> List[str]:
    return load_profile()["enrollment_risk_patterns"]


def get_search_queries() -> List[str]:
    return load_profile()["search_queries"]


def get_raw_text() -> str:
    return load_profile()["raw_text"]


# ── Cache invalidation ──

def invalidate_candidate_cache() -> None:
    """Clear the module-level profile and candidate caches.

    Call this after switching the active DB profile so that
    get_profile_config() and load_candidate_preferences() serve the new
    profile on the next call.
    """
    global _profile, _candidate_preferences
    _profile = None
    _candidate_preferences = None


# ── Free-text resume extraction ──

# Common tech skills recognised in raw resume text.
_KNOWN_SKILLS: frozenset[str] = frozenset({
    # Languages
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
    "scala", "r", "ruby", "php", "swift", "kotlin", "matlab", "julia", "bash", "sql",
    # ML / AI
    "pytorch", "tensorflow", "keras", "scikit-learn", "huggingface", "transformers",
    "langchain", "llamaindex", "openai", "anthropic", "llm", "rag",
    "vector database", "embedding", "fine-tuning", "nlp", "computer vision",
    "deep learning", "machine learning", "neural network", "generative ai",
    # Backend
    "fastapi", "django", "flask", "express", "spring boot", "graphql", "rest api",
    "grpc", "kafka", "rabbitmq", "celery", "redis", "nginx",
    # Data
    "spark", "hadoop", "airflow", "dbt", "pandas", "numpy", "polars", "dask",
    "etl", "data pipeline", "data warehouse", "snowflake", "databricks",
    # Databases
    "postgresql", "mysql", "sqlite", "mongodb", "elasticsearch", "pinecone",
    "weaviate", "chroma", "qdrant", "dynamodb", "cassandra",
    # Cloud / infra
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "github actions", "ci/cd", "linux", "git", "mlflow", "wandb",
    # Frontend
    "react", "vue", "angular", "next.js", "html", "css",
})

# Ordered role patterns — first match wins per group.
_ROLE_PATTERNS: list[tuple[str, str]] = [
    (r'\bapplied\s+(ai|ml)\s+(engineer|scientist|researcher)\b', "applied ai engineer"),
    (r'\bllm\s+(engineer|developer|researcher)\b', "llm engineer"),
    (r'\brag\s+(engineer|developer)\b', "rag engineer"),
    (r'\b(machine\s*learning|ml)\s+(engineer|researcher|scientist)\b', "ml engineer"),
    (r'\bai\s+(engineer|researcher|scientist)\b', "ai engineer"),
    (r'\bnlp\s+(engineer|researcher|scientist)\b', "nlp engineer"),
    (r'\bdata\s+scientist\b', "data scientist"),
    (r'\bdata\s+engineer\b', "data engineer"),
    (r'\bdata\s+analyst\b', "data analyst"),
    (r'\bsoftware\s+(engineer|developer|swe)\b', "software engineer"),
    (r'\bbackend\s+(engineer|developer)\b', "backend engineer"),
    (r'\bfull.?stack\s+(engineer|developer)\b', "full stack engineer"),
    (r'\bfrontend\s+(engineer|developer)\b', "frontend engineer"),
    (r'\bplatform\s+engineer\b', "platform engineer"),
    (r'\b(devops|site\s*reliability)\s+engineer\b', "devops engineer"),
    (r'\bsre\b', "sre"),
    (r'\bcloud\s+engineer\b', "cloud engineer"),
    (r'\bresearch\s+(scientist|engineer)\b', "research scientist"),
    (r'\bproduct\s+manager\b', "product manager"),
    (r'\bproduct\s+designer\b', "product designer"),
    (r'\b(graphic|ui|ux)\s+designer\b', "designer"),
    (r'\bmechanical\s+engineer\b', "mechanical engineer"),
    (r'\belectrical\s+engineer\b', "electrical engineer"),
    (r'\bcivil\s+engineer\b', "civil engineer"),
    (r'\bchemical\s+engineer\b', "chemical engineer"),
    (r'\bnurse\b', "nurse"),
    (r'\bfinancial\s+analyst\b', "financial analyst"),
    (r'\bbusiness\s+analyst\b', "business analyst"),
    (r'\bmarketing\s+(manager|analyst|specialist)\b', "marketing specialist"),
    (r'\baccountant\b', "accountant"),
    (r'\bproject\s+manager\b', "project manager"),
]

_US_LOCATION_PATTERNS: list[str] = [
    "united states", "usa", "u.s.a", "u.s.", "remote us", "remote",
    "new york", "san francisco", "seattle", "austin", "boston",
    "chicago", "los angeles", "denver", "atlanta", "dallas",
    "washington dc", "washington, d.c", "sf bay area", "bay area",
    "silicon valley", "new jersey", "california", "texas", "washington",
    "massachusetts", "new york, ny", "ny, ny",
]

_EXPERIENCE_SENIOR_SIGNALS: frozenset[str] = frozenset({
    "senior", "lead", "staff", "principal", "director", "vp", "head of",
    "manager", "architect",
})
_EXPERIENCE_ENTRY_SIGNALS: frozenset[str] = frozenset({
    "new grad", "new graduate", "entry level", "entry-level", "junior",
    "associate", "intern", "internship", "co-op", "fresh graduate",
    "recent graduate", "0-2 years", "0–2 years", "1-2 years",
})

_VISA_SPONSORSHIP_SIGNALS: frozenset[str] = frozenset({
    "opt", "cpt", "h-1b", "h1b", "h1-b", "will require sponsorship",
    "require visa sponsorship", "requires sponsorship", "need sponsorship",
    "needs sponsorship", "visa sponsorship required",
})
_VISA_AUTHORIZED_SIGNALS: frozenset[str] = frozenset({
    "authorized to work", "work authorization", "us citizen", "u.s. citizen",
    "permanent resident", "green card", "ead", "no sponsorship required",
    "do not require sponsorship", "does not require sponsorship",
})


def extract_profile_from_text(raw_text: str) -> dict:
    """Extract a structured search profile from pasted raw resume text.

    Local-only heuristic extraction — zero network calls.

    Returns a dict matching the ``profiles.extracted_json`` schema::

        {
            "roles": ["data engineer", "ml engineer"],
            "skills": ["python", "pytorch", "sql"],
            "locations": ["United States", "Remote"],
            "experience_level": "entry_level",
            "visa_needed": True,
            "work_modes": ["remote", "hybrid"],
            "verified": {"roles": True, "skills": True, ...},
            "missing": ["locations"]
        }
    """
    text = raw_text or ""
    text_lower = text.lower()

    skills = _detect_skills(text_lower)
    roles = _detect_roles(text_lower)
    locations = _detect_locations(text_lower)
    experience_level = _detect_experience_level(text_lower)
    visa_needed = _detect_visa_needed(text_lower)
    work_modes = _detect_work_modes(text_lower)

    verified = {
        "roles": bool(roles),
        "skills": bool(skills),
        "locations": bool(locations),
        "experience": bool(experience_level),
        "visa": True,  # always determined; False is a valid value
    }
    missing = [k for k, v in verified.items() if not v]

    return {
        "roles": roles,
        "skills": sorted(skills),
        "locations": locations if locations else ["United States", "Remote"],
        "experience_level": experience_level or "entry_level",
        "visa_needed": visa_needed,
        "work_modes": work_modes if work_modes else ["remote", "hybrid", "onsite"],
        "verified": verified,
        "missing": missing,
    }


def _detect_skills(text_lower: str) -> list[str]:
    found = []
    for skill in sorted(_KNOWN_SKILLS):
        # Use word-boundary matching for short tokens to avoid false positives
        if len(skill) <= 2:
            pattern = r'(?<![a-z])' + re.escape(skill) + r'(?![a-z])'
        else:
            pattern = re.escape(skill)
        if re.search(pattern, text_lower):
            found.append(skill)
    return found


def _detect_roles(text_lower: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern, canonical in _ROLE_PATTERNS:
        if re.search(pattern, text_lower) and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
    return found


def _detect_locations(text_lower: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    # Prefer "Remote" entry if remote is found
    has_remote = bool(re.search(r'\bremote\b', text_lower))
    if has_remote and "Remote" not in seen:
        found.append("Remote")
        seen.add("Remote")
    for loc in _US_LOCATION_PATTERNS:
        if loc in ("remote",):
            continue  # already handled
        if loc in text_lower and loc not in seen:
            # Capitalise nicely
            display = " ".join(w.capitalize() for w in loc.split())
            found.append(display)
            seen.add(loc)
    # Always include "United States" if any US signal present
    if found and "United States" not in seen:
        found.append("United States")
    return found


def _detect_experience_level(text_lower: str) -> str:
    # Check explicit seniority signals first
    for signal in _EXPERIENCE_SENIOR_SIGNALS:
        if re.search(r'\b' + re.escape(signal) + r'\b', text_lower):
            return "senior"
    for signal in _EXPERIENCE_ENTRY_SIGNALS:
        if re.search(r'\b' + re.escape(signal) + r'\b', text_lower):
            return "entry_level"
    # Fallback: count years mentioned in experience
    year_matches = re.findall(r'(\d+)\+?\s*years?\s+of\s+(experience|work)', text_lower)
    if year_matches:
        max_years = max(int(m[0]) for m in year_matches)
        if max_years >= 5:
            return "senior"
        if max_years >= 3:
            return "mid_level"
        return "entry_level"
    return ""


def _detect_visa_needed(text_lower: str) -> bool:
    # Explicit "will need sponsorship" signals → True
    for signal in _VISA_SPONSORSHIP_SIGNALS:
        if signal in text_lower:
            return True
    # Explicit "no sponsorship needed" signals → False
    for signal in _VISA_AUTHORIZED_SIGNALS:
        if signal in text_lower:
            return False
    # Default: no sponsorship assumed unless stated
    return False


def _detect_work_modes(text_lower: str) -> list[str]:
    modes: list[str] = []
    if re.search(r'\bremote\b', text_lower):
        modes.append("remote")
    if re.search(r'\bhybrid\b', text_lower):
        modes.append("hybrid")
    if re.search(r'\b(on.?site|in.?office|in.?person)\b', text_lower):
        modes.append("onsite")
    return modes
