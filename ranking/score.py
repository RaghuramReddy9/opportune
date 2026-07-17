"""
ranking/score.py — Resume-based scoring and ranking.

Computes a 0-100 match score for each job based on:
- Strong keyword matches from resume
- Title-based skill inference (for short listings)
- Role target matching
- Project relevance
- OPT/visa signal detection
- Education level check
"""
import re
import logging
from typing import Tuple

from resume.resume_profile import (
    load_profile, get_all_skills, get_strong_keywords, get_projects,
    get_role_targets, load_candidate_preferences,
)
from ranking.guardrails import is_research_engineering_role, source_quality_weight, location_verdict, freshness_sort_rank
from ranking.targeting import classify_role_families, classify_target_level, role_family_score, target_level_score

logger = logging.getLogger("ranking.score")

# ── Title-based skill inference map ──
# When we only have a title (e.g. GitHub lists), infer skills from title keywords
TITLE_SKILL_MAP = {
    "llm": ["llm", "large language model", "generative ai", "nlp"],
    "rag": ["rag", "retrieval augmented", "retrieval", "vector search"],
    "nlp": ["nlp", "natural language", "text", "classification", "embeddings"],
    "ml": ["machine learning", "ml", "deep learning"],
    "ai": ["ai", "artificial intelligence", "machine learning"],
    "agent": ["ai agents", "agents", "multi-agent", "langgraph", "langchain"],
    "langchain": ["langchain", "langgraph", "ai agents"],
    "langgraph": ["langgraph", "langchain", "multi-agent"],
    "fastapi": ["fastapi", "rest api", "backend", "python"],
    "data": ["data pipelines", "etl", "data engineering", "sql", "python"],
    "research": ["research", "applied research", "evaluation"],
    "backend": ["backend systems", "rest api", "fastapi", "python", "docker"],
    "platform": ["platform", "infrastructure", "mlops", "docker"],
    "security": ["ai security", "guardrails", "observability", "logging"],
    "eval": ["evaluation", "observability", "mlflow"],
    "fine-tun": ["fine-tuning", "fine tuning", "model deployment", "hugging face"],
    "vector": ["vector search", "vector database", "embeddings", "faiss"],
    "deploy": ["model deployment", "mlops", "mlflow", "docker", "ci/cd"],
    "scientist": ["machine learning", "deep learning", "evaluation", "nlp", "research"],
    "engineer": ["python", "fastapi", "rest api", "docker", "ci/cd"],
    "software": ["python", "fastapi", "rest api", "backend", "docker"],
    "applied": ["applied research", "machine learning", "nlp", "evaluation"],
    "generative": ["generative ai", "llm", "nlp", "fine-tuning", "rag"],
    "content": ["nlp", "embeddings", "classification"],
    "ecolog": ["embeddings", "evaluation", "nlp"],
    "health": ["nlp", "fine-tuning", "evaluation", "rag"],
    "healthcare": ["nlp", "fine-tuning", "evaluation", "rag"],
    "medical": ["nlp", "fine-tuning", "evaluation", "rag"],
    "document": ["rag", "retrieval", "vector search", "embeddings", "chunking"],
    "search": ["vector search", "embeddings", "semantic search", "retrieval"],
    "intelligence": ["ai", "machine learning", "nlp", "llm"],
    "co-op": ["internship", "entry level", "early career"],
    "apprentice": ["entry level", "early career", "internship"],
    "fellow": ["research", "entry level", "internship"],
    "resident": ["research", "entry level", "internship"],
    "assistant": ["ai agents", "llm", "python", "fastapi"],
    "qa": ["fine-tuning", "evaluation", "nlp", "question answering"],
    "nlp intern": ["nlp", "machine learning", "python", "evaluation", "fine-tuning"],
    "ml intern": ["machine learning", "python", "deep learning", "evaluation"],
    "ai intern": ["ai", "machine learning", "python", "llm"],
    "cv intern": ["deep learning", "machine learning", "python", "nlp"],
    "gen ai": ["generative ai", "llm", "nlp", "fine-tuning"],
    "automation": ["python", "etl", "data pipelines", "ai agents", "fastapi"],
    "inference": ["model deployment", "fine-tuning", "mlops", "python"],
    "train": ["fine-tuning", "model deployment", "machine learning", "python"],
    "pipeline": ["data pipelines", "etl", "python", "mlops", "docker"],
}

# ── Project title-keyword mapping ──
TITLE_PROJECT_MAP = {
    "enterprise ai operations assistant": [
        "agent", "operations", "support", "workflow", "automation", "assistant",
        "platform", "tool", "llm", "ai", "engineer", "software", "backend",
        "devops", "reliability", "mlops", "infrastructure",
    ],
    "multi-agent workflow automation assistant": [
        "workflow", "automation", "research", "scientist", "agent", "multi-agent", "nlp", "evaluation",
        "synthesis", "analysis", "investigation", "experiment", "study",
        "language", "text", "classification", "reasoning",
    ],
    "financial document intelligence assistant": [
        "document", "search", "retrieval", "rag", "vector", "knowledge",
        "data scientist", "data", "analyst", "intelligence", "finance",
        "legal", "information", "content", "insight", "analytics",
    ],
    "medassist-qa — fine-tuned llm application": [
        "nlp", "qa", "question", "fine-tun", "model", "medical",
        "healthcare", "clinical", "health", "bio", "science",
        "scientist", "deep learning", "machine learning",
    ],
}


def is_excluded(text: str, *, title: str = "") -> Tuple[bool, str]:
    """Check if a job should be excluded. Hard exclusions + profile exclusions."""
    text_lower = text.lower()
    title_lower = title.lower()

    # Dynamic exclusions from profile
    try:
        from resume.resume_profile import get_exclusion_patterns
        dynamic_exclusions = get_exclusion_patterns()
    except Exception as e:
        logger.warning("Failed to load dynamic exclusions: %s", e)
        dynamic_exclusions = set()

    positive_non_exclusions = {
        "recent graduate",
        "new graduate",
        "early career",
        "entry level",
        "associate",
        "junior",
        "engineer i",
        "0–2 years",
        "0-2 years",
        "master's graduate",
        "graduate intern",
        "students encouraged to apply",
        "currently pursuing degree preferred",
    }
    for pattern in dynamic_exclusions:
        p = pattern.strip().lower()
        if (
            not p
            or p.startswith("do not")
            or "don't" in p
            or "welcome" in p
            or "prefer" in p
            or "strict exclusion rules" in p
            or p in positive_non_exclusions
        ):
            continue
        # Check as a whole word/phrase to prevent partial word matches
        if re.search(r'\b' + re.escape(p) + r'\b', text_lower):
            return True, f"Profile exclusion: {p}"

    # GAP 8: Applied Scientist can be production-facing or research-heavy.
    # Exclude only variants with clear academic/research requirements.
    if re.search(r"\bapplied\s+scientist\b", text_lower):
        research_heavy = [
            r"\bphd\s+(required|preferred|in)\b",
            r"\bpublication(s)?\b",
            r"\btop[-\s]tier\s+conference\b",
            r"\bresearch\s+agenda\b",
            r"\bnovel\s+(algorithm|model|method)",
            r"\btheoretical\b",
            r"\bpeer[-\s]reviewed\b",
            r"\bpostdoctoral\b",
        ]
        if any(re.search(pattern, text_lower) for pattern in research_heavy):
            return True, "Applied Scientist research-heavy"

    # ── Research role exclusions ──
    # Exclude roles that are primarily research (not applied engineering)
    research_only_patterns = [
        (r"\bresearch\s+scientist\b", "Research Scientist"),
        (r"\bresearch\s+assistant\b", "Research Assistant"),
        (r"\bresearch\s+intern\b(?!.*\b(engineering|engineer|applied)\b)", "Research Intern"),
        (r"\bphd\s+intern\b", "PhD Intern"),
        (r"\bphd\s+fellow\b", "PhD Fellow"),
        (r"\bai\s+safety\s+fellow\b", "AI Safety Fellow"),
        (r"\bai\s+resident\b", "AI Resident"),
        (r"\bml\s+resident\b", "ML Resident"),
        (r"\bpostdoc\b", "Postdoc"),
        (r"\bpublication[-\s]focused\b", "Publication-focused"),
        (r"\bpure\s+research\b", "Pure research"),
        (r"\btheoretical\b", "Theoretical"),
        (r"\bspeech\s+researcher\b", "Speech Researcher"),
        (r"\bcomputer\s+vision\s+researcher\b", "CV Researcher (research-only)"),
        (r"\bnlp\s+researcher\b(?!.*\b(engineering|engineer|applied)\b)", "NLP Researcher"),
    ]
    for pattern, reason in research_only_patterns:
        if re.search(pattern, text_lower):
            return True, reason

    senior_titles = [
        (r"\bsenior\b", "senior"),
        (r"\bstaff\b", "staff"),
        (r"\bprincipal\b", "principal"),
        (r"\blead\b(?!ing)", "lead"),
        (r"\bmanager\b", "manager"),
        (r"\bdirector\b", "director"),
    ]
    for pattern, reason in senior_titles:
        if re.search(pattern, title_lower):
            return True, reason

    experience_exclusions = [
        (r"\b5\+\s*years\b", "5+ years"),
        (r"\b7\+\s*years\b", "7+ years"),
        (r"\b10\+\s*years\b", "10+ years"),
    ]
    for pattern, reason in experience_exclusions:
        if re.search(pattern, text_lower):
            return True, reason

    if re.search(r"\bunpaid\b|\bvolunteer\s+only\b", text_lower):
        return True, "unpaid"

    return False, ""


def detect_enrollment_requirement(text: str) -> dict:
    """Detect roles that may require current school enrollment."""
    text_lower = text.lower()
    result = {"enrollment_risk": False, "reason": ""}

    patterns = [
        (r"\bmust\s+be\s+(currently\s+)?enrolled\b", "Must be currently enrolled"),
        (r"\bcurrently\s+enrolled\s+in\b", "Currently enrolled requirement"),
        (r"\breturn(ing)?\s+to\s+(school|college|university)\b", "Return-to-school requirement"),
        (r"\bmust\s+return\s+to\s+school\b", "Must return to school"),
        (r"\bcontinuing\s+student\b", "Continuing student requirement"),
        (r"\bgraduat(?:e|ing)\s+(after|between)\b", "Graduation-window requirement"),
        (r"\bexpected\s+graduation\s+(date\s+)?(of|between|after)\b", "Expected graduation window"),
    ]
    for pattern, reason in patterns:
        if re.search(pattern, text_lower):
            result.update({"enrollment_risk": True, "reason": reason})
            return result

    return result


def detect_education_level(text: str) -> dict:
    """Detect education level requirements."""
    text_lower = text.lower()
    result = {"phd_required": False, "phd_preferred": False, "bs_ms_friendly": False, "unknown": True, "reason": ""}

    if re.search(r"\bphd\s+(required|only)\b|\bdoctorate\s+required\b|\bmust\s+be\s+enrolled\s+in\s+phd\b", text_lower):
        result.update({"phd_required": True, "unknown": False, "reason": "PhD required"})
        return result

    if re.search(r"\bphd\s+preferred\b|\bdoctorate\s+preferred\b", text_lower):
        result.update({"phd_preferred": True, "unknown": False, "reason": "PhD preferred"})
        return result

    if re.search(r"\bbachelor'?s?\s*(or|/|and)\s*master'?s?\b|\bundergraduate\b|\bgraduate\s+student\b|\bms\s+student\b|\bcurrent\s+student\b", text_lower):
        result.update({"bs_ms_friendly": True, "unknown": False, "reason": "BS/MS friendly"})
        return result

    result["reason"] = "No education signal"
    return result


def detect_opt_signal(text: str) -> dict:
    """Detect OPT-friendly signals. Uses both profile patterns and core defaults."""
    text_lower = text.lower()

    # Load dynamic OPT patterns from profile
    try:
        from resume.resume_profile import get_opt_risk_patterns, get_opt_friendly_signals
        dynamic_risks = get_opt_risk_patterns()
        dynamic_friendly = get_opt_friendly_signals()
    except Exception as e:
        logger.warning("Failed to load dynamic OPT patterns: %s", e)
        dynamic_risks = set()
        dynamic_friendly = set()

    # 1. High risk check (first priority)
    # Check dynamic profile risks first
    for pattern in dynamic_risks:
        p = pattern.strip().lower()
        if p and p in text_lower:
            return {"signal": "High Risk", "score": -30, "reason": f"Profile OPT/Visa risk: {p}"}

    high_risk = [
        "no visa sponsorship", "no sponsorship now or in the future",
        "no f-1", "no opt", "no cpt",
        "u.s. citizen only", "us citizen only", "u.s. citizens only",
        "green card only", "permanent resident only",
        "active security clearance required", "ts/sci required", "itar restricted",
    ]
    for pattern in high_risk:
        if pattern in text_lower:
            return {"signal": "High Risk", "score": -30, "reason": f"OPT/Visa risk: {pattern}"}

    # 2. Explicit support must win over broad profile tokens such as "OPT".
    explicit_support_patterns = [
        r"\b(?:visa\s+)?sponsorship\s+(?:is\s+)?(?:available|provided|supported|offered)\b",
        r"\b(?:stem\s+)?opt\s+sponsorship\s+(?:is\s+)?(?:available|provided|supported|offered)\b",
        r"\bf-?1(?:\s+opt)?\s+sponsorship\s+(?:is\s+)?(?:available|provided|supported|offered)\b",
        r"\bwe\s+(?:do\s+)?sponsor\s+(?:f-?1|opt|international)\s+(?:candidates|applicants|employees)\b",
    ]
    for pattern in explicit_support_patterns:
        if re.search(pattern, text_lower):
            return {"signal": "Strong", "score": 5, "reason": f"Explicit sponsorship support: {pattern}"}

    # 3. Dynamic strong/friendly check
    for pattern in dynamic_friendly:
        p = pattern.strip().lower()
        if p and p in text_lower:
            score = 5 if any(x in p for x in ("stem", "sponsor", "e-verify")) else 3
            signal = "Strong" if score == 5 else "Yes"
            return {"signal": signal, "score": score, "reason": f"Profile OPT-friendly: {p}"}

    strong = [
        "stem opt", "sponsorship available", "visa sponsorship",
        "international students welcome", "open to work authorization",
        "e-verify", "sponsorship provided", "cpt sponsorship",
        "opt sponsorship", "f-1 sponsorship",
    ]
    for s in strong:
        if s in text_lower:
            return {"signal": "Strong", "score": 5, "reason": f"Strong: {s}"}

    regular = [
        "opt", "cpt", "f-1", "stem opt",
        "international students", "recent graduates", "new graduates",
        "early career", "entry level", "internship",
        "graduate internship", "master's students",
        "students encouraged to apply", "authorized to work in the u.s.",
        "work authorization", "e-verify",
    ]
    for s in regular:
        if s in text_lower:
            return {"signal": "Yes", "score": 3, "reason": f"OPT-friendly: {s}"}

    return {"signal": "Unknown", "score": 0, "reason": "No OPT signal"}


def compute_resume_score(job: dict) -> dict:
    """Compute a differentiated 0-100 resume match score."""
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    company = job.get("company", "").lower()
    full_text = f"{title} {company} {description} {job.get('full_text', '')}".lower()

    strong_kws = get_strong_keywords()
    all_skills = get_all_skills()
    projects = get_projects()
    role_targets = get_role_targets()
    from config import get_profile_config

    configured_roles = {
        str(role).strip().lower()
        for role in get_profile_config().get("target_roles", [])
        if str(role).strip()
    }
    role_targets["high"] = set(role_targets.get("high", set())) | configured_roles

    # Title-based skill inference
    title_skill_boost = set()
    for trigger, inferred_skills in TITLE_SKILL_MAP.items():
        if trigger in title:
            for s in inferred_skills:
                title_skill_boost.add(s)

    # Strong keyword matches
    matched_strong = [kw for kw in strong_kws if kw in full_text or kw in title_skill_boost]
    missing_strong = [kw for kw in strong_kws if kw not in matched_strong]

    # Skill gap analysis
    all_tech_keywords = [
        "tensorflow", "pytorch", "jax", "spark", "kafka", "airflow", "dbt",
        "snowflake", "databricks", "kubernetes", "terraform", "ansible",
        "swift", "kotlin", "go", "rust", "java", "c++", "scala",
        "react", "angular", "vue", "nextjs", "typescript",
        "mongodb", "postgresql", "redis", "elasticsearch",
        "tableau", "powerbi", "looker", "hadoop",
        "sagemaker", "vertex ai", "azure ml", "watson",
    ]
    def _skill_covers_tech(tech: str) -> bool:
        tech_norm = tech.lower().replace(" ", "").replace("-", "")
        for skill in all_skills:
            skill_norm = str(skill).lower().replace(" ", "").replace("-", "")
            if not skill_norm:
                continue
            if tech_norm == skill_norm or tech_norm in skill_norm or skill_norm in tech_norm:
                return True
        return False

    candidate_missing_skills = [
        tech for tech in all_tech_keywords
        if tech in full_text and not _skill_covers_tech(tech)
    ]

    # Role target match
    role_match_score = 0
    matched_roles = []
    for role in role_targets.get("high", set()):
        role_words = role.split()
        if any(word in title for word in role_words if len(word) > 3):
            role_match_score += 3
            matched_roles.append(role)
        elif any(word in full_text for word in role_words if len(word) > 3):
            role_match_score += 1
            matched_roles.append(role)

    # Project relevance
    best_project = ""
    best_project_score = 0
    for proj_name, proj_data in projects.items():
        proj_score = 0
        proj_full = proj_data.get("full_text", "")
        for kw in matched_strong:
            if kw in proj_full:
                proj_score += 1
        for role in proj_data.get("best_roles", set()):
            if role.lower() in full_text or role.lower() in title:
                proj_score += 2
        proj_keywords = TITLE_PROJECT_MAP.get(proj_name, [])
        for kw in proj_keywords:
            if kw in title:
                proj_score += 1
        if proj_score > best_project_score:
            best_project_score = proj_score
            best_project = proj_data["name"]

    # Heuristic fallback
    if not best_project:
        if "agent" in title or "assistant" in title or "workflow" in title:
            best_project = "Enterprise AI Operations Assistant"
        elif "research" in title or "scientist" in title or "evaluation" in title:
            best_project = "Multi-Agent Workflow Automation Assistant"
        elif "data" in title or "analyst" in title or "document" in title:
            best_project = "Financial Document Intelligence Assistant"
        elif "model" in title or "qa" in title or "fine" in title or "nlp" in title:
            best_project = "MedAssist-QA — Fine-Tuned LLM Application"
        best_project_score = 1

    opt_result = detect_opt_signal(full_text)
    edu = detect_education_level(full_text)
    enrollment = detect_enrollment_requirement(full_text)
    candidate_preferences = load_candidate_preferences()
    target_level = classify_target_level(job.get("title", ""))
    target_score = target_level_score(job, candidate_preferences)
    target_role_families = classify_role_families(job)
    target_role_family_score = role_family_score(job)

    # Weighted scoring rubric. A 100 is intentionally rare; most good jobs
    # should land in the 70-92 range, and missing evidence applies hard caps.
    loc_verdict = location_verdict(job)
    description_text = (job.get("description") or job.get("full_text") or "").strip()
    has_description_confidence = len(description_text) >= 80

    preferred_family_weights = {
        "applied_ai": 9,
        "genai_llm_rag": 8,
        "ai_agents": 8,
        "backend_ai_systems": 7,
        "fde_ai": 7,
        "solutions_ai": 6,
    }
    role_family_component = min(
        25,
        sum(preferred_family_weights.get(fam, 4) for fam in target_role_families),
    )
    if target_role_families:
        role_family_component = max(14, role_family_component)

    project_component = min(20, best_project_score * 4)
    if best_project and best_project_score > 0:
        project_component = max(project_component, 8)

    skill_component = min(18, len(matched_strong) * 2)
    if any(kw in matched_strong for kw in ("rag", "rag pipelines", "llm", "agentic ai", "langgraph", "langchain")):
        skill_component = min(18, skill_component + 4)

    if target_level in candidate_preferences.get("target_levels", []):
        level_component = 15
    elif target_level == "unknown":
        level_component = 6
    elif target_score > 0:
        level_component = 8
    else:
        level_component = 0

    location_auth_component = 0
    if loc_verdict["status"] in {"us_verified", "configured_verified"}:
        location_auth_component += 7
    elif loc_verdict["status"] == "trusted_company_unknown":
        location_auth_component += 3
    if opt_result["signal"] == "Strong":
        location_auth_component += 3
    elif opt_result["signal"] == "Yes":
        location_auth_component += 2
    elif opt_result["signal"] == "Unknown":
        location_auth_component += 1
    location_auth_component = min(10, location_auth_component)

    freshness_rank = freshness_sort_rank(job.get("freshness", "Unknown"))
    freshness_component = max(0, 5 - freshness_rank)
    source_component = 2 if source_quality_weight(job.get("source", "")) >= 20 else 1
    freshness_source_component = min(7, freshness_component + source_component)

    description_component = 5 if has_description_confidence else 2 if description_text else 0

    score_components = {
        "role_family": role_family_component,
        "project_fit": project_component,
        "skill_fit": skill_component,
        "level_fit": level_component,
        "location_auth": location_auth_component,
        "freshness_source": freshness_source_component,
        "description_confidence": description_component,
    }

    raw_score = sum(score_components.values())
    missing_penalty = min(18, len(candidate_missing_skills) * 4)
    phd_penalty = 40 if edu["phd_required"] else 0
    raw_score = raw_score + opt_result["score"] - missing_penalty - phd_penalty

    score_caps: list[str] = []
    cap = 100
    if not target_role_families:
        cap = min(cap, 55)
        score_caps.append("no_applied_ai_family_cap")
        if re.search(r"\b(data\s+engineer|etl|warehouse|dashboard|reporting)\b", full_text) and not re.search(r"\b(llm|rag|agent|gen\s*ai|generative\s+ai|applied\s+ai)\b", full_text):
            cap = min(cap, 45)
            score_caps.append("plain_data_role_cap")
    if not loc_verdict["allowed"]:
        cap = min(cap, int(loc_verdict.get("score_cap") or 40))
        score_caps.append("location_rejected_cap")
    elif loc_verdict.get("score_cap"):
        cap = min(cap, int(loc_verdict["score_cap"]))
        score_caps.append("unknown_location_cap")
    if target_level == "unknown":
        cap = min(cap, 72)
        score_caps.append("unknown_level_cap")
    if opt_result["signal"] == "Unknown":
        cap = min(cap, 85)
        score_caps.append("unknown_auth_cap")
    if not best_project:
        cap = min(cap, 78)
        score_caps.append("no_project_match_cap")
    if not has_description_confidence:
        cap = min(cap, 65)
        score_caps.append("thin_description_cap")
    if edu["phd_required"]:
        cap = min(cap, 35)
        score_caps.append("phd_required_cap")

    normalized = max(0, min(cap, int(raw_score)))

    priority = "A" if normalized >= 82 else "B" if normalized >= 55 else "C"
    confidence = "high" if normalized >= 82 and not score_caps else "medium" if normalized >= 55 else "low"

    return {
        "resume_match_score": normalized,
        "priority": priority,
        "matched_keywords": matched_strong[:10],
        "missing_keywords": missing_strong[:10],
        "candidate_missing_skills": candidate_missing_skills[:8],
        "matched_roles": matched_roles[:5],
        "best_matching_project": best_project,
        "project_relevance_score": best_project_score,
        "opt_signal": opt_result["signal"],
        "opt_signal_reason": opt_result["reason"],
        "education_level": edu,
        "enrollment_risk": enrollment["enrollment_risk"],
        "enrollment_risk_reason": enrollment["reason"],
        "target_level": target_level,
        "target_level_score": target_score,
        "target_role_families": target_role_families,
        "target_role_family_score": target_role_family_score,
        "candidate_target_match": target_level in candidate_preferences.get("target_levels", []),
        "kw_count": len(matched_strong),
        "location_bonus": score_components["location_auth"],
        "location_verdict": loc_verdict,
        "score_components": score_components,
        "score_caps": score_caps,
        "score_confidence": confidence,
    }


def rank_job(job: dict) -> dict:
    """Add all ranking fields to a normalized job dict."""
    full_text = f"{job.get('title', '')} {job.get('company', '')} {job.get('description', '')} {job.get('full_text', '')}"

    excluded, exclude_reason = is_excluded(full_text, title=str(job.get("title", "")))
    job["excluded"] = excluded
    job["exclude_reason"] = exclude_reason

    score = compute_resume_score(job)
    job["resume_match_score"] = score["resume_match_score"]
    job["priority"] = score["priority"]
    job["matched_keywords"] = score["matched_keywords"]
    job["missing_keywords"] = score["missing_keywords"]
    job["candidate_missing_skills"] = score["candidate_missing_skills"]
    job["matched_roles"] = score["matched_roles"]
    job["best_matching_project"] = score["best_matching_project"]
    job["opt_signal"] = score["opt_signal"]
    job["opt_signal_reason"] = score["opt_signal_reason"]
    job["education_level"] = score["education_level"]
    job["enrollment_risk"] = score.get("enrollment_risk", False)
    job["enrollment_risk_reason"] = score.get("enrollment_risk_reason", "")
    job["target_level"] = score.get("target_level")
    job["target_level_score"] = score.get("target_level_score")
    job["target_role_families"] = score.get("target_role_families", [])
    job["target_role_family_score"] = score.get("target_role_family_score", 0)
    job["candidate_target_match"] = score.get("candidate_target_match", False)
    job["location_bonus"] = score.get("location_bonus", 0)
    job["location_verdict"] = score.get("location_verdict", {})
    job["score_components"] = score.get("score_components", {})
    job["score_caps"] = score.get("score_caps", [])
    job["score_confidence"] = score.get("score_confidence", "low")

    job["why_matches"] = _generate_why_matches(job, score)
    job["why_risky"] = _generate_why_risky(job, score)
    job["application_angle"] = _generate_application_angle(job, score)

    return job


def _plausible_ranking_candidate(job: dict, candidate_preferences: dict) -> bool:
    """Cheaply reject rows that the full ranking gates would always discard."""
    title = str(job.get("title") or "").lower()
    if not title:
        return False
    if re.search(r"\bphd\b", title) and not re.search(
        r"\b(phd\s+or|phd\s+preferred|master'?s?\s+or\s+phd)\b", title
    ):
        return False

    target_level = classify_target_level(title)
    allowed_levels = set(candidate_preferences.get("target_levels", [])) | set(
        candidate_preferences.get("secondary_levels", [])
    )
    if target_level not in allowed_levels:
        if target_level not in {"internship", "co_op"}:
            return False
        detail = f"{job.get('description', '')} {job.get('full_text', '')}".lower()
        if not re.search(
            r"\b(recent\s+graduates?|new\s+grads?|new\s+graduates?|graduates?\s+welcome|master'?s\s+graduates?|final[-\s]?year\s+graduates?|graduated\s+within\s+the\s+last\s+\d+\s+(?:months|years)|alumni|early[-\s]?career\s+candidates?|non[-\s]?current[-\s]?student)\b",
            detail,
        ):
            return False

    strong_title = re.search(
        r"\b(ai|ml|nlp|llm|rag|genai|mlops|agentic|agents?|retrieval|inference|vector|embedding|automation)\b|"
        r"machine learning|deep learning|generative|gen ai|langchain|langgraph|multi-agent|data science|data engineer|pyspark|etl|pipeline",
        title,
    )
    if strong_title:
        return True
    if not re.search(r"software engineer|software developer|backend|api|fastapi|flask|python|model|deploy|cloud|docker|aws|azure", title):
        return False
    detail = f"{job.get('description', '')} {job.get('full_text', '')}".lower()
    return bool(re.search(
        r"machine learning|deep learning|\bnlp\b|\bllm\b|generative ai|\brag\b|retrieval|ai agent|multi-agent|langchain|langgraph|mlops|vector|embedding|fine-tun|model training|data science|pyspark|data engineer|etl pipeline|ai/ml|artificial intelligence",
        detail,
    ))


def filter_and_rank(jobs: list) -> list:
    """Filter and rank jobs using resume-based scoring.

    Only includes roles that are:
    1. Not excluded (research, senior, visa, etc.)
    2. Target role type (intern, junior, entry-level, new-grad, associate)
    3. Relevant to applied AI/ML engineering
    """
    load_profile()
    results = []
    excluded_count = {
        "strict": 0, "phd_required": 0, "not_relevant": 0,
        "not_target_level": 0, "research": 0, "low_keyword_match": 0,
    }

    # Target levels are configurable from candidate_profile.yaml.
    # the candidate's current primary targets are new-grad, entry-level, and junior roles;
    # internships/co-ops are secondary and must pass the eligibility gate later.
    candidate_preferences = load_candidate_preferences()
    plausible_jobs = [
        job for job in jobs if _plausible_ranking_candidate(job, candidate_preferences)
    ]
    logger.info("Cheap candidate prefilter: %d -> %d", len(jobs), len(plausible_jobs))

    for job in plausible_jobs:
        job = rank_job(job)
        if job.get("excluded"):
            excluded_count["strict"] += 1
            continue
        if not job.get("education_match", True) and job.get("education_level", {}).get("phd_required"):
            excluded_count["phd_required"] += 1
            continue

        title = job.get("title", "").lower()

        # Exclude PhD-only roles
        if re.search(r"\bphd\b", title) and not re.search(r"\b(phd\s+or|phd\s+preferred|master'?s?\s+or\s+phd)\b", title):
            excluded_count["strict"] += 1
            continue

        # Must match a configured primary target level. Internships/co-ops are
        # not default targets for the candidate after Master's completion, but may pass to
        # the eligibility gate only when the text positively says graduate /
        # Master's / early-career non-current-student candidates are eligible.
        target_level = job.get("target_level", "unknown")
        allowed_levels = set(candidate_preferences.get("target_levels", [])) | set(candidate_preferences.get("secondary_levels", []))
        full_text_for_level = f"{job.get('title', '')} {job.get('description', '')} {job.get('full_text', '')}".lower()
        graduate_friendly_internship = (
            target_level in {"internship", "co_op"}
            and re.search(
                r"\b(recent\s+graduates?|new\s+grads?|new\s+graduates?|graduates?\s+welcome|master'?s\s+graduates?|final[-\s]?year\s+graduates?|graduated\s+within\s+the\s+last\s+\d+\s+(?:months|years)|alumni|early[-\s]?career\s+candidates?|non[-\s]?current[-\s]?student)\b",
                full_text_for_level,
            )
        )
        if target_level not in allowed_levels and not graduate_friendly_internship:
            excluded_count["not_target_level"] += 1
            continue

        # Research-titled roles need explicit product/engineering evidence.
        if not is_research_engineering_role(job.get("title", ""), job.get("description", "") or job.get("full_text", "")):
            excluded_count["research"] += 1
            continue

        # Two-tier relevance filter:
        # Uses word-boundary matching for short ambiguous keywords (ai, ml, nlp, rag, etl)
        # to prevent false matches like 'ai' inside 'affairs', 'ml' inside 'formula', etc.
        def _kw_in_title(kw: str, t: str) -> bool:
            """Word-boundary safe keyword match for short terms."""
            # Short keywords (<=4 chars) or all-letter abbreviations need boundaries
            if len(kw) <= 4 and kw.isalpha() and " " not in kw:
                return bool(re.search(r'\b' + re.escape(kw) + r'\b', t))
            return kw in t

        # Tier 1 — strong AI/ML signal in title → always pass
        strong_ai_title_kw = [
            "ai", "ml", "machine learning", "deep learning",
            "nlp", "llm", "generative", "gen ai", "genai",
            "rag", "retrieval", "agent", "agents", "multi-agent",
            "langchain", "langgraph",
            "mlops", "inference", "vector", "embedding", "faiss",
            "data science", "data engineer", "pyspark", "spark", "etl",
            "automation", "pipeline",
        ]
        has_strong_title_signal = any(_kw_in_title(kw, title) for kw in strong_ai_title_kw)

        # Tier 2 — generic tech title → also require AI/ML signal in the full description
        generic_tech_title_kw = [
            "software engineer", "software developer", "backend", "api",
            "fastapi", "flask", "python", "model", "deploy", "cloud",
            "docker", "aws", "azure",
        ]
        has_generic_title = any(_kw_in_title(kw, title) for kw in generic_tech_title_kw)

        full_text_lower = job.get("full_text", "").lower() or job.get("description", "").lower()
        ai_ml_text_kw = [
            "machine learning", "deep learning", "nlp", "llm", "generative ai",
            "rag", "retrieval", "ai agent", "multi-agent", "langchain", "langgraph",
            "mlops", "vector", "embedding", "fine-tun", "model training",
            "data science", "pyspark", "data engineer", "etl pipeline",
            "ai/ml", "ai ml", "artificial intelligence",
        ]
        has_ai_ml_in_text = any(kw in full_text_lower for kw in ai_ml_text_kw)

        if has_strong_title_signal:
            pass  # Always include
        elif has_generic_title and has_ai_ml_in_text:
            pass  # Generic title but confirmed AI/ML role from description
        else:
            excluded_count["not_relevant"] += 1
            continue

        # Applied-AI family gate: the default profile expects roles that sound like applied AI
        # products/systems (RAG, LLM apps, agents, GenAI, AI systems), not
        # plain Machine Learning Engineer or Data Engineer queues.
        if not job.get("target_role_families"):
            excluded_count["not_relevant"] += 1
            continue

        # GAP 9: require at least two strong keyword matches after relevance checks.
        if len(job.get("matched_keywords", [])) < 2:
            excluded_count["low_keyword_match"] += 1
            continue

        # Location guardrail: hard-exclude non-U.S./ambiguous board roles. Direct
        # ATS rows with blank location can proceed only with scoring caps for enrichment.
        loc_status = job.get("location_verdict") or location_verdict(job)
        job["location_verdict"] = loc_status
        if not loc_status.get("allowed", False):
            excluded_count["not_relevant"] += 1
            continue

        job["source_quality_weight"] = source_quality_weight(job.get("source", ""))
        results.append(job)

    priority_order = {"A": 0, "B": 1, "C": 2}
    results.sort(key=lambda j: (
        priority_order.get(j.get("priority", "C"), 3),
        -j.get("source_quality_weight", 0),
        -j.get("resume_match_score", 0),
    ))

    logger.info(
        "Filtered %d → %d (%d A, %d B, %d C) | Excluded: %s",
        len(jobs), len(results),
        sum(1 for j in results if j.get("priority") == "A"),
        sum(1 for j in results if j.get("priority") == "B"),
        sum(1 for j in results if j.get("priority") == "C"),
        excluded_count,
    )
    return results


def _generate_why_matches(job: dict, score: dict) -> str:
    parts = []
    matched_roles = score.get("matched_roles", [])
    if matched_roles:
        parts.append(f"Title matches target roles: **{', '.join(matched_roles[:3])}**")
    matched_kws = score.get("matched_keywords", [])
    if matched_kws:
        parts.append(f"Skills overlap: {', '.join(matched_kws[:6])}")
    if score.get("best_matching_project"):
        parts.append(f"Best project match: **{score['best_matching_project']}** (relevance: {score.get('project_relevance_score', 0)})")
    if not parts:
        parts.append("Weak match — limited skill overlap")
    return ". ".join(parts) + "."


def _generate_why_risky(job: dict, score: dict) -> str:
    risks = []
    if score.get("opt_signal") == "High Risk":
        risks.append(f"OPT/Visa risk: {score.get('opt_signal_reason', '')}")
    elif score.get("opt_signal") == "Unknown":
        risks.append("OPT/Visa status unknown")
    edu = score.get("education_level", {})
    if edu.get("phd_required"):
        risks.append("PhD required — the candidate has MS")
    elif edu.get("phd_preferred"):
        risks.append("PhD preferred — may be at a disadvantage")
    if score.get("enrollment_risk"):
        reason = score.get("enrollment_risk_reason", "Current enrollment requirement")
        risks.append(f"Enrollment risk: {reason}")
    missing = score.get("candidate_missing_skills", [])
    if missing:
        risks.append(f"Job uses tech not in resume: {', '.join(missing[:5])}")
    if not risks:
        risks.append("Low risk — no major red flags")
    return ". ".join(risks) + "."


def _generate_application_angle(job: dict, score: dict) -> str:
    angles = []
    if score.get("best_matching_project"):
        angles.append(f"Lead with **{score['best_matching_project']}** project")
    matched_kws = score.get("matched_keywords", [])
    if "rag" in matched_kws or "retrieval" in matched_kws:
        angles.append("Emphasize RAG and retrieval experience")
    if "langgraph" in matched_kws or "langchain" in matched_kws or "agent" in matched_kws:
        angles.append("Highlight multi-agent system building")
    if "fastapi" in matched_kws or "rest api" in matched_kws:
        angles.append("Focus on FastAPI and backend API development")
    if "fine-tuning" in matched_kws:
        angles.append("Highlight fine-tuning and model optimization work")
    if "nlp" in matched_kws:
        angles.append("Emphasize NLP and language model experience")
    if not angles:
        angles.append("Emphasize Python, SQL, and AI/ML project experience")
    return ". ".join(angles) + "."
