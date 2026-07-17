"""
ranking/targeting.py — Candidate target-level and role-family matching.

Target level is configurable because candidates have different experience levels.
The default profile targets U.S. new-grad, entry-level, junior, associate,
Engineer I, 0–2 years, and early-career applied AI product/system roles:
RAG, LLM applications, AI agents, GenAI apps, backend AI systems, AI solutions,
and forward-deployed AI. Plain Machine Learning Engineer and Data Engineer
roles are intentionally not target families.
Internship/co-op roles are not default targets; eligibility may allow them only
when the posting explicitly accepts recent graduates / Master's graduates.
"""
from __future__ import annotations

import re


_EARLY_CAREER_LEVELS = {
    "new_grad",
    "entry_level",
    "junior",
    "associate",
    "engineer_i",
    "zero_to_two_years",
    "early_career",
}


def _has(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _requires_over_two_years(text: str) -> bool:
    """Detect obvious requirements above the candidate's 0–2 year target."""
    return _has(r"\b(?:at\s+least\s+|minimum\s+of\s+)?(?:[3-9]|1\d)\+?\s+years?\b", text)


def _has_explicit_early_career_signal(text: str) -> bool:
    return any(
        _has(pattern, text)
        for pattern in [
            r"\bnew\s*grad\b",
            r"\bnew[-\s]?graduate\b",
            r"\buniversity\s+grad\b",
            r"\bentry[-\s]?level\b",
            r"\bearly[-\s]?career\b",
            r"\bassociate\b",
            r"\bjunior\b",
            r"\bjr\.?\b",
            r"\b(?:software|ai|machine\s+learning|ml|data|backend|forward\s+deployed)?\s*engineer\s+i\b",
            r"\b(?:swe|sde)\s*1\b",
            r"\b0\s*[-–—]\s*2\s+years?\b",
        ]
    )


def classify_target_level(title: str) -> str:
    """Classify a role title into a normalized target level."""
    text = (title or "").lower()

    if re.search(r"\b(senior|sr\.?|staff|principal|lead|manager|director)\b", text):
        return "not_target"

    # If a generic title advertises 3+ years and does not also identify itself
    # as junior/entry/new-grad/Engineer I, keep it out of the candidate's queue.
    if _requires_over_two_years(text) and not _has_explicit_early_career_signal(text):
        return "not_target"

    if re.search(r"\b(new\s*grad|new[-\s]?graduate|new\s+college\s+grad|new\s+college\s+graduate|new\s+grads|university\s+grad|graduate\s+(software|ai|machine learning|data)?\s*engineer)\b", text):
        return "new_grad"
    if re.search(r"\b0\s*[-–—]\s*2\s+years?\b", text):
        return "zero_to_two_years"
    if re.search(r"\b(?:software|ai|machine\s+learning|ml|data|backend|forward\s+deployed|software\s+development|product)?\s*engineer\s+i\b", text):
        return "engineer_i"
    if re.search(r"\b(?:software|ai|machine\s+learning|ml|data|backend|software\s+development|product)\s+engineer\s+1\b", text):
        return "engineer_i"
    if re.search(r"\b(?:swe|sde)\s*1\b", text):
        return "engineer_i"
    if re.search(r"\bassociate\b", text):
        return "associate"
    if re.search(r"\bentry[-\s]?level\b", text):
        return "entry_level"
    if re.search(r"\bearly[-\s]?career\b", text):
        return "early_career"
    if re.search(r"\b(junior|jr\.?)\b", text):
        return "junior"
    if re.search(r"\b(intern|internship)\b", text):
        return "internship"
    if re.search(r"\b(co[-\s]?op|coop)\b", text):
        return "co_op"
    return "unknown"


def target_level_score(job: dict, preferences: dict) -> int:
    """Return target-level score contribution for ranking.

    Primary target levels are strongly boosted. Explicitly non-target roles are
    a hard negative. Internships/co-ops are intentionally not rewarded unless a
    user's profile explicitly lists them; the eligibility gate still controls
    whether graduate-friendly internships can enter Notion.
    """
    level = classify_target_level(job.get("title", ""))
    if level == "not_target":
        return -100
    if level in set(preferences.get("target_levels", [])):
        return 100
    if level in set(preferences.get("secondary_levels", [])):
        return 35
    if level == "unknown":
        return 0
    return -25


def classify_role_families(job: dict) -> list[str]:
    """Return the candidate's preferred applied AI product/system role families.

    Plain Machine Learning Engineer and Data Engineer roles are intentionally
    not target families. A role needs to sound like applied AI — RAG, LLM apps,
    agents, GenAI, AI systems, AI solutions, or forward-deployed AI.
    """
    text = "\n".join(
        str(job.get(field, ""))
        for field in ("title", "description", "full_text", "details")
        if job.get(field)
    ).lower()
    families: list[str] = []
    patterns = {
        "applied_ai": [
            r"\bapplied\s+ai\s*[/\s]\s*(ml\s+)?(engineer|scientist)\b",
            r"\bai\s*[/\s]\s*ml\s+(engineer|scientist)\b",
            r"\bartificial\s+intelligence\s+engineer\b",
            r"\bai\s+(software\s+)?engineer\b",
            r"\bsoftware\s+engineer\b.*\b(ai|llm|rag|agentic|agent|gen\s*ai|generative\s+ai)\b",
            r"\b(ai|llm|rag|agentic|agent|gen\s*ai|generative\s+ai)\b.*\bsoftware\s+engineer\b",
            r"\bai[-\s]?first\s+software\s+engineer\b",
            r"\bai\s+product\s+engineer\b",
            r"\bfull\s+stack\s+ai\s+engineer\b",
            r"\bai\s+engineer\b",
            r"\bml\s+engineer\b.*\b(ai|llm|rag|agentic|agent|gen\s*ai|generative\s+ai)\b",
        ],
        "genai_llm_rag": [r"\bgen\s*ai\b", r"\bgenerative\s+ai\b", r"\bllm\b", r"\brag\b", r"\blangchain\b", r"\blanggraph\b"],
        "ai_agents": [r"\bai\s+agents?\b", r"\bagentic\b", r"\bagent\s+workflows?\b", r"\btool\s+use\b"],
        "backend_ai_systems": [r"\bbackend\b.*\b(ai|llm|rag|agent|gen\s*ai)\b", r"\bai\s+systems\b"],
        "solutions_ai": [r"\bai\s+solutions\s+engineer\b"],
        "fde_ai": [r"\bforward\s+deployed\s+(ai\s+)?engineer\b"],
    }
    for family, family_patterns in patterns.items():
        if any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in family_patterns):
            families.append(family)
    return families


def role_family_score(job: dict) -> int:
    """Score boost for the candidate's preferred role families."""
    return 20 * len(classify_role_families(job))
