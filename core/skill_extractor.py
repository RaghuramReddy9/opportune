"""Extract a canonical set of skills from free‑text job descriptions.

The extractor uses a small, version‑controlled taxonomy (data/skill_taxonomy.yaml)
to map tokens and simple composites to canonical skill names. It is intentionally
lightweight – no external NLP dependencies – so it can be called for every job
in the pipeline without noticeable overhead.
"""

import re
import sys
from pathlib import Path
from typing import List, Set

# Load taxonomy once at import time. Setuptools data-files land under
# ``sys.prefix`` in an installed wheel, while a source checkout keeps the same
# file at the repository root.
_PROJECT_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data" / "skill_taxonomy.yaml"
_INSTALLED_TAXONOMY_PATH = Path(sys.prefix) / "data" / "skill_taxonomy.yaml"
_TAXONOMY_PATH = (
    _PROJECT_TAXONOMY_PATH if _PROJECT_TAXONOMY_PATH.exists() else _INSTALLED_TAXONOMY_PATH
)


def _load_taxonomy() -> dict:
    """Return the raw taxonomy as dict {cluster: [skill, ...]}."""
    import yaml

    if not _TAXONOMY_PATH.exists():
        return {}
    with open(_TAXONOMY_PATH, "rt", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# Build reverse lookup: skill_lower -> canonical_skill
_TAXONOMY = _load_taxonomy()
_SKILL_MAP: dict[str, str] = {}
for cluster, skills in _TAXONOMY.items():
    for skill in skills:
        _SKILL_MAP[skill.lower()] = skill
        # also map common composites without spaces (e.g. "reactjs")
        _SKILL_MAP[skill.lower().replace(" ", "")] = skill

# Additional aliases for common variations not caught by the above rules
_EXTRA_ALIASES = {
    "react.js": "React",
    "reactjs": "React",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    # Add more as needed
}
_SKILL_MAP.update(_EXTRA_ALIASES)


def extract_skills(text: str) -> List[str]:
    """Return a sorted list of unique canonical skills found in *text*.

    The algorithm:
      1. Extract word‑like tokens (allowing +, #, .).
      2. Direct lowercase map.
      3. Try removing internal spaces (e.g. "react js").
      4. Strip trailing punctuation (e.g., "reactjs." -> "reactjs").
      5. De‑duplicate and sort for deterministic output.

    Parameters
    ----------
    text: str
        Job description or any free‑text field.

    Returns
    -------
    List[str]
        Canonical skill names, e.g. ["Python", "PyTorch", "AWS"].
    """
    if not text:
        return []

    found: Set[str] = set()

    # First scan multi-word aliases against normalized text. The token pass below
    # cannot see phrases such as "Azure OpenAI" or "Delta Lake".
    normalized_text = re.sub(r"\s+", " ", text.lower())
    for alias, canonical in sorted(_SKILL_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if " " not in alias:
            continue
        pattern = r"(?<![a-z0-9]){}(?![a-z0-9])".format(re.escape(alias))
        if re.search(pattern, normalized_text):
            found.add(canonical)

    # Match sequences of letters, digits, +, #, ., and -
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\+\.\#\-]+", text)

    for raw in tokens:
        lowered = raw.lower()
        # Direct hit
        if lowered in _SKILL_MAP:
            found.add(_SKILL_MAP[lowered])
            continue
        # Remove internal spaces (the tokeniser already split on non‑alnum,
        # so we also try to join with previous token? Simpler: try no‑space version)
        no_space = lowered.replace(" ", "")
        if no_space in _SKILL_MAP:
            found.add(_SKILL_MAP[no_space])
            continue
        # Strip trailing punctuation (e.g., '.' or ',' that may be attached)
        stripped = no_space
        while stripped and not stripped[-1].isalnum():
            stripped = stripped[:-1]
        if stripped and stripped in _SKILL_MAP:
            found.add(_SKILL_MAP[stripped])
            continue
        # Handle common hyphenated variants (e.g. "c++" already captured by regex)
        # Nothing else needed for now.

    return sorted(found)


if __name__ == "__main__":  # pragma: no cover
    # Simple smoke test
    sample = "We are looking for a Python engineer with experience in PyTorch, AWS Lambda, and React.js."
    print(extract_skills(sample))