"""Benchmark dataset validation and leakage/privacy gates."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

_REQUIRED = {
    "case_id",
    "candidate_set_id",
    "profile_id",
    "listing_id",
    "split",
    "profile",
    "listing",
    "labels",
    "provenance",
    "labeling",
}
_VALID_SPLITS = {"development", "validation", "final_test"}
_PROHIBITED_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:sk|pk|api)[-_][A-Za-z0-9_-]{12,}\b", re.I),
    re.compile(r"(?:^|[\s\"'])(?:/home/|/Users/|[A-Za-z]:\\Users\\)"),
)
_PROHIBITED_KEYS = {"email", "phone", "address", "resume_text", "api_key", "notes", "raw_url"}


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_walk_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_walk_keys(item) for item in value), set())
    return set()


def validate_cases(cases: list[dict], *, min_cases: int = 320) -> dict:
    errors: list[str] = []
    if len(cases) < min_cases:
        errors.append(f"dataset has {len(cases)} cases; at least {min_cases} required")

    case_ids = [str(case.get("case_id", "")) for case in cases]
    duplicates = [case_id for case_id, count in Counter(case_ids).items() if count > 1]
    if duplicates:
        errors.append(f"duplicate case_id values: {', '.join(sorted(duplicates)[:5])}")

    sets: dict[str, list[dict]] = defaultdict(list)
    leakage: dict[tuple[str, str], set[str]] = defaultdict(set)
    for index, case in enumerate(cases):
        missing = sorted(_REQUIRED - set(case))
        if missing:
            errors.append(f"case {index} missing required keys: {', '.join(missing)}")
            continue
        split = str(case.get("split"))
        if split not in _VALID_SPLITS:
            errors.append(f"case {case['case_id']} has invalid split {split!r}")
        sets[str(case["candidate_set_id"])].append(case)
        if split == "final_test" and len(case.get("labeling", {}).get("labeler_ids", [])) < 2:
            errors.append(f"final_test case {case['case_id']} is not double-labeled")
        if _walk_keys(case) & _PROHIBITED_KEYS:
            errors.append(f"case {case['case_id']} contains prohibited private fields")
        serialized = json.dumps(case, sort_keys=True)
        if any(pattern.search(serialized) for pattern in _PROHIBITED_PATTERNS):
            errors.append(f"case {case['case_id']} contains a prohibited private/secret pattern")

        provenance = case.get("provenance", {})
        listing = case.get("listing", {})
        identities = {
            "content_hash": provenance.get("content_hash"),
            "canonical_job_id": listing.get("canonical_job_id"),
            "duplicate_cluster_id": case.get("duplicate_cluster_id"),
        }
        for kind, value in identities.items():
            if value:
                leakage[(kind, str(value))].add(split)

    for set_id, members in sets.items():
        if len(members) != 10:
            errors.append(f"candidate set {set_id} must contain exactly 10 cases; found {len(members)}")
        splits = {str(member.get("split")) for member in members}
        if len(splits) > 1:
            errors.append(f"candidate set {set_id} crosses splits")

    for (kind, value), splits in leakage.items():
        if len(splits) > 1:
            errors.append(f"cross-split leakage for {kind}={value}")

    return {
        "ok": not errors,
        "case_count": len(cases),
        "candidate_set_count": len(sets),
        "split_counts": dict(Counter(str(case.get("split")) for case in cases)),
        "errors": errors,
    }
