"""Match job skills against a local skill profile and compute gaps.

Components:
  - load_user_profile(): reads tracker/profile/skills.yaml or profile/skills.example.yaml
  - skill_match(job_text, profile): returns (match_score, missing_skills)

The match score is a proficiency‑weighted Jaccard‑like ratio:
    overlap = Σ min(user_level[skill], 5) for each skill in job
    max_possible = Σ 5 for each skill in job   (user level capped at 5)
    match = overlap / max_possible   (0‑1)

Missing skills are those job skills where the user level is < 3
(considered “not yet competent”). The threshold can be tweaked.
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

from .skill_extractor import extract_skills


class SkillProfile(dict):
    """Case-insensitive skill profile with missing skills defaulting to 0."""

    @staticmethod
    def _key(key) -> str:
        return str(key).strip().lower()

    def __getitem__(self, key):
        return super().__getitem__(self._key(key))

    def get(self, key, default=None):
        if default is None:
            default = 0
        return super().get(self._key(key), default)

    def __contains__(self, key):
        return super().__contains__(self._key(key))


def load_user_profile(profile_path: Path | None = None) -> Dict[str, int]:
    """Read a user skill profile and return {skill: level (0-5)}."""
    import yaml

    project_root = Path(__file__).resolve().parents[1]
    candidates = [
        profile_path,
        project_root / "tracker" / "profile" / "skills.yaml",
        project_root / "profile" / "skills.example.yaml",
        Path(sys.prefix) / "profile" / "skills.example.yaml",
    ]
    path = next((p for p in candidates if p and p.exists()), None)
    if not path:
        return {}
    with open(path, "rt", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return SkillProfile({str(s["name"]).strip().lower(): int(s.get("level", 0)) for s in data.get("skills", [])})


def skill_match(job_text: str, user_profile: Dict[str, int]) -> Tuple[float, List[str]]:
    """Return (match_score, missing_skills) for a job description.

    Parameters
    ----------
    job_text: str
        Any free‑text field that contains the job description (we use full_text).
    user_profile: dict
        Output of load_user_profile().

    Returns
    -------
    match_score: float
        Proficiency‑weighted overlap in range [0.0, 1.0].
    missing_skills: list[str]
        Skills from the job where user level < 3 (needs development).
    """
    job_skills = set(extract_skills(job_text))
    if not job_skills:
        return 0.0, []

    overlap = 0
    normalized_profile = SkillProfile({str(k).strip().lower(): int(v) for k, v in user_profile.items()})
    normalized_job_skills = {skill.lower(): skill for skill in job_skills}
    for skill_key in normalized_job_skills:
        user_level = normalized_profile.get(skill_key, 0)
        overlap += min(user_level, 5)   # cap at 5

    max_possible = len(job_skills) * 5
    match_score = overlap / max_possible if max_possible else 0.0

    missing = [skill_key for skill_key in sorted(normalized_job_skills) if normalized_profile.get(skill_key, 0) < 3]
    return match_score, missing


if __name__ == "__main__":  # pragma: no cover
    # Quick self‑test
    profile = load_user_profile()
    print("Loaded profile:", profile)
    sample = "We need a Python engineer with PyTorch, AWS, and Docker experience."
    score, miss = skill_match(sample, profile)
    print(f"Match: {score:.2f}, Missing: {miss}")