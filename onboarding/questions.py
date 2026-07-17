"""Structured clarification questions derived from a resume analysis."""
from __future__ import annotations


def _role_options(analysis: dict) -> list[dict]:
    suggestions = analysis.get("suggested_roles") or []
    options: list[dict] = []
    for item in suggestions:
        if isinstance(item, str):
            options.append({"value": item, "label": item, "description": "Suggested from your resume."})
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        options.append(
            {
                "value": title,
                "label": title,
                "description": str(item.get("reason") or "Suggested from your resume."),
                "confidence": float(item.get("confidence") or 0),
            }
        )
    if not options:
        for role in analysis.get("roles") or []:
            options.append({"value": role, "label": role, "description": "Found in your resume."})
    return options


def build_questions(analysis: dict) -> list[dict]:
    """Return the five required, stable clarification questions."""
    locations = [str(item) for item in analysis.get("locations") or []]
    return [
        {
            "id": "role_priorities",
            "number": 1,
            "required": True,
            "kind": "multi",
            "max_selections": 3,
            "title": "Which roles should we prioritize?",
            "helper": "Choose up to three. Put the work you want most first.",
            "options": _role_options(analysis),
        },
        {
            "id": "work_focus",
            "number": 2,
            "required": True,
            "kind": "single",
            "title": "What kind of work do you want to spend most of your time doing?",
            "helper": "This helps us separate roles you can do from roles you actually want.",
            "options": [
                {"value": "ai_product_engineering", "label": "Build AI-powered products", "description": "User-facing features, APIs, RAG, agents, and evaluation."},
                {"value": "model_engineering", "label": "Train or improve models", "description": "Fine-tuning, experimentation, inference, and model quality."},
                {"value": "platform_infrastructure", "label": "Build platforms and infrastructure", "description": "Backend systems, data pipelines, reliability, and developer tooling."},
                {"value": "customer_facing", "label": "Solve customer problems directly", "description": "Forward-deployed, solutions, and integration work."},
                {"value": "flexible", "label": "Keep the search broad", "description": "Use my evidence and show several realistic directions."},
            ],
        },
        {
            "id": "experience_levels",
            "number": 3,
            "required": True,
            "kind": "multi",
            "title": "Which experience levels should we include?",
            "helper": "We will exclude levels you do not select.",
            "options": [
                {"value": "internship", "label": "Internship", "description": "Student or graduate-eligible internships."},
                {"value": "new_grad", "label": "New graduate", "description": "Dedicated university or recent-graduate roles."},
                {"value": "entry_level", "label": "Entry level", "description": "Roles designed for early-career candidates."},
                {"value": "junior", "label": "Junior / Engineer I", "description": "Usually zero to two years of experience."},
                {"value": "mid_level", "label": "Mid level", "description": "Usually two to five years of experience."},
            ],
        },
        {
            "id": "location_preferences",
            "number": 4,
            "required": True,
            "kind": "location",
            "title": "Where and how can you work?",
            "helper": "Confirm locations, work modes, and whether relocation is realistic.",
            "suggested_locations": locations,
            "work_mode_options": ["remote", "hybrid", "onsite"],
        },
        {
            "id": "authorization",
            "number": 5,
            "required": True,
            "kind": "authorization",
            "title": "What should we know about work authorization and deal-breakers?",
            "helper": "We never infer sponsorship needs from nationality, education, or location.",
            "options": [
                {"value": "none", "label": "No sponsorship needed", "description": "I can work without current or future sponsorship."},
                {"value": "needs_sponsorship", "label": "Sponsorship required", "description": "Prioritize employers that explicitly support sponsorship."},
                {"value": "opt_cpt", "label": "OPT / CPT", "description": "I may need future sponsorship after temporary work authorization."},
                {"value": "custom", "label": "I need to explain", "description": "Let me add a short note for the search rules."},
            ],
        },
    ]
