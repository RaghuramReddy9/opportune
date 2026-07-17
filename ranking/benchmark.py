"""Labeled ranking benchmark and release quality gates."""
from __future__ import annotations

import argparse
import copy
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from pipeline.scrape import filter_ready_to_apply_jobs
from ranking import filter_and_rank
from ranking.guardrails import apply_freshness_trust

DEFAULT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v1_jobs.json"
QUALITY_GATES = {
    "exact_bucket_accuracy": 0.80,
    "apply_precision": 1.0,
    "surface_recall": 0.90,
    "unsafe_false_applies": 0,
}

# The release benchmark represents an early-career U.S. candidate who needs
# sponsorship. It must not inherit the machine owner's active dashboard profile
# or config.yaml, otherwise the same wheel can pass or fail on different hosts.
BENCHMARK_PROFILE = {
    "locations": ["United States", "Remote US"],
    "timeline": {"max_age_days": 7},
}
BENCHMARK_PREFERENCES = {
    "education_status": "unknown",
    "target_levels": [
        "new_grad",
        "entry_level",
        "junior",
        "associate",
        "engineer_i",
        "zero_to_two_years",
        "early_career",
    ],
    "secondary_levels": [],
    "internship_policy": "explicit_graduate_eligibility_required",
    "visa_status": {
        "needs_sponsorship_future": True,
        "opt_eligible": True,
    },
    "visa_policy": "custom",
    "location_policy": {"country": "US", "remote_us_ok": True},
    "preferred_locations": ["United States", "Remote US"],
    "timeline": {"max_age_days": 7},
}


@contextmanager
def _isolated_benchmark_profile():
    """Keep quality results independent from local user preferences."""
    from resume import resume_profile

    previous_profile = resume_profile._profile
    previous_preferences = resume_profile._candidate_preferences
    resume_profile._profile = None
    resume_profile._candidate_preferences = None
    try:
        with (
            patch.object(
                resume_profile,
                "_PROFILE_PATH",
                resume_profile._PROFILE_TEMPLATE_PATH,
            ),
            patch("config.get_profile_config", return_value=copy.deepcopy(BENCHMARK_PROFILE)),
            patch(
                "resume.resume_profile.load_candidate_preferences",
                return_value=copy.deepcopy(BENCHMARK_PREFERENCES),
            ),
            patch(
                "ranking.score.load_candidate_preferences",
                return_value=copy.deepcopy(BENCHMARK_PREFERENCES),
            ),
        ):
            yield
    finally:
        resume_profile._profile = previous_profile
        resume_profile._candidate_preferences = previous_preferences


def classify_fixture(fixture: dict) -> dict:
    job = copy.deepcopy(
        {key: value for key, value in fixture.items() if key != "expected"}
    )
    ranked = filter_and_rank([job])
    if not ranked:
        return {
            "predicted": "skip",
            "score": int(job.get("resume_match_score", 0) or 0),
            "reasons": [job.get("exclude_reason") or "ranking_filter"],
        }
    candidate = apply_freshness_trust(ranked[0])
    ready, review, excluded = filter_ready_to_apply_jobs([candidate])
    if ready:
        predicted, chosen = "apply_now", ready[0]
    elif review:
        predicted, chosen = "watch", review[0]
    else:
        predicted, chosen = "skip", excluded[0]
    return {
        "predicted": predicted,
        "score": int(chosen.get("resume_match_score", 0) or 0),
        "reasons": chosen.get("eligibility_reason_codes", []),
    }


def evaluate(fixtures_path: Path = DEFAULT_FIXTURES) -> dict:
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    rows = []
    with _isolated_benchmark_profile():
        for fixture in fixtures:
            result = classify_fixture(fixture)
            rows.append({
                "id": fixture["id"],
                "expected": fixture["expected"],
                **result,
                "correct": result["predicted"] == fixture["expected"],
            })

    total = len(rows)
    exact = sum(row["correct"] for row in rows) / total if total else 0.0
    predicted_apply = [row for row in rows if row["predicted"] == "apply_now"]
    apply_precision = (
        sum(row["expected"] == "apply_now" for row in predicted_apply)
        / len(predicted_apply)
        if predicted_apply else 0.0
    )
    expected_surface = [row for row in rows if row["expected"] != "skip"]
    surface_recall = (
        sum(row["predicted"] != "skip" for row in expected_surface)
        / len(expected_surface)
        if expected_surface else 0.0
    )
    unsafe_false_applies = sum(
        row["predicted"] == "apply_now" and row["expected"] != "apply_now"
        for row in rows
    )
    metrics = {
        "exact_bucket_accuracy": round(exact, 4),
        "apply_precision": round(apply_precision, 4),
        "surface_recall": round(surface_recall, 4),
        "unsafe_false_applies": unsafe_false_applies,
        "fixture_count": total,
    }
    gate_results = {
        "exact_bucket_accuracy": metrics["exact_bucket_accuracy"]
        >= QUALITY_GATES["exact_bucket_accuracy"],
        "apply_precision": metrics["apply_precision"]
        >= QUALITY_GATES["apply_precision"],
        "surface_recall": metrics["surface_recall"]
        >= QUALITY_GATES["surface_recall"],
        "unsafe_false_applies": metrics["unsafe_false_applies"]
        <= QUALITY_GATES["unsafe_false_applies"],
    }
    return {
        "ok": all(gate_results.values()),
        "metrics": metrics,
        "quality_gates": QUALITY_GATES,
        "gate_results": gate_results,
        "errors": [row for row in rows if not row["correct"]],
        "rows": rows,
        "fixtures_path": str(fixtures_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate labeled Opportune ranking fixtures"
    )
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate(args.fixtures)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("PASS" if report["ok"] else "FAIL", report["metrics"])
        for error in report["errors"]:
            print(
                f"- {error['id']}: expected={error['expected']} "
                f"predicted={error['predicted']} score={error['score']}"
            )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
