"""Public benchmark dataset and metric contracts."""
from __future__ import annotations

from benchmarks.report import evaluate_predictions
from benchmarks.validate import validate_cases


def _case(case_id: str, set_id: str, split: str, decision: str, *, unsafe: bool = False, labelers: int = 2) -> dict:
    return {
        "case_id": case_id,
        "candidate_set_id": set_id,
        "profile_id": "synthetic-profile",
        "listing_id": f"listing-{case_id}",
        "duplicate_cluster_id": None,
        "split": split,
        "profile": {"target_roles": ["Applied AI Engineer"], "locations": ["United States"]},
        "listing": {"title": "Synthetic role", "canonical_job_id": f"job-{case_id}"},
        "labels": {"final_decision": decision, "unsafe_to_recommend": unsafe},
        "provenance": {"kind": "synthetic", "content_hash": f"sha256-{case_id}"},
        "labeling": {"labeler_ids": [f"labeler-{index}" for index in range(labelers)]},
    }


def test_validator_rejects_candidate_sets_without_exactly_ten_cases():
    report = validate_cases([_case("1", "set-1", "development", "ready")], min_cases=1)

    assert report["ok"] is False
    assert any("exactly 10" in error for error in report["errors"])


def test_validator_rejects_cross_split_leakage_and_final_test_single_label():
    first = _case("1", "set-a", "development", "ready")
    second = _case("2", "set-b", "final_test", "review", labelers=1)
    second["provenance"]["content_hash"] = first["provenance"]["content_hash"]
    cases = [first] * 10 + [second] * 10
    for index, case in enumerate(cases):
        case = dict(case)
        case["case_id"] = f"case-{index}"
        cases[index] = case

    report = validate_cases(cases, min_cases=20)

    assert report["ok"] is False
    assert any("cross-split" in error for error in report["errors"])
    assert any("double-labeled" in error for error in report["errors"])


def test_validator_rejects_private_or_secret_patterns():
    cases = [_case(str(index), "set-1", "development", "ready") for index in range(10)]
    cases[0]["profile"]["email"] = "person@example.com"

    report = validate_cases(cases, min_cases=10)

    assert any("prohibited" in error for error in report["errors"])


def test_report_computes_ready_precision_top_k_and_unsafe_gate():
    cases = []
    predictions = []
    for index in range(10):
        decision = "ready" if index < 5 else "excluded"
        case = _case(str(index), "set-1", "final_test", decision, unsafe=index == 9)
        cases.append(case)
        predictions.append(
            {
                "case_id": case["case_id"],
                "decision": decision,
                "score": 100 - index,
                "reason_codes": [],
            }
        )

    report = evaluate_predictions(cases, predictions)

    assert report["metrics"]["ready_precision"] == 1.0
    assert report["metrics"]["precision_at_5"] == 1.0
    assert report["metrics"]["precision_at_10"] == 0.5
    assert report["metrics"]["unsafe_ready_count"] == 0
