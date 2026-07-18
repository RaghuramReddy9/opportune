"""Deterministic public benchmark metric report."""
from __future__ import annotations

from collections import defaultdict


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate_predictions(cases: list[dict], predictions: list[dict]) -> dict:
    prediction_by_id = {str(row["case_id"]): row for row in predictions}
    rows = []
    missing = []
    for case in cases:
        case_id = str(case["case_id"])
        prediction = prediction_by_id.get(case_id)
        if prediction is None:
            missing.append(case_id)
            continue
        rows.append(
            {
                "case_id": case_id,
                "candidate_set_id": str(case["candidate_set_id"]),
                "expected": case["labels"]["final_decision"],
                "unsafe": bool(case["labels"].get("unsafe_to_recommend", False)),
                "predicted": prediction["decision"],
                "score": float(prediction.get("score", 0)),
                "reason_codes": list(prediction.get("reason_codes", [])),
                "required_reason_codes": list(case["labels"].get("required_reason_codes", [])),
                "forbidden_reason_codes": list(case["labels"].get("forbidden_reason_codes", [])),
            }
        )

    predicted_ready = [row for row in rows if row["predicted"] == "ready"]
    expected_ready = [row for row in rows if row["expected"] == "ready"]
    predicted_review = [row for row in rows if row["predicted"] == "review"]
    expected_excluded = [row for row in rows if row["expected"] == "excluded"]
    expected_surface = [row for row in rows if row["expected"] != "excluded"]

    sets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        sets[row["candidate_set_id"]].append(row)
    p5_values = []
    p10_values = []
    for members in sets.values():
        ranked = sorted(members, key=lambda row: row["score"], reverse=True)
        top5 = ranked[:5]
        top10 = ranked[:10]
        p5_values.append(_ratio(sum(row["expected"] == "ready" for row in top5), len(top5)))
        p10_values.append(_ratio(sum(row["expected"] == "ready" for row in top10), len(top10)))

    explanation_consistent = 0
    for row in rows:
        reasons = set(row["reason_codes"])
        if set(row["required_reason_codes"]).issubset(reasons) and not (
            set(row["forbidden_reason_codes"]) & reasons
        ):
            explanation_consistent += 1

    unsafe_ready = sum(row["predicted"] == "ready" and row["unsafe"] for row in rows)
    false_ready = sum(row["predicted"] == "ready" and row["expected"] != "ready" for row in rows)
    missed_ready = sum(row["expected"] == "ready" and row["predicted"] != "ready" for row in rows)
    metrics = {
        "ready_precision": _ratio(sum(row["expected"] == "ready" for row in predicted_ready), len(predicted_ready)),
        "precision_at_5": round(sum(p5_values) / len(p5_values), 4) if p5_values else 0.0,
        "precision_at_10": round(sum(p10_values) / len(p10_values), 4) if p10_values else 0.0,
        "surface_recall": _ratio(sum(row["predicted"] != "excluded" for row in expected_surface), len(expected_surface)),
        "false_positive_rate": _ratio(false_ready, len(rows) - len(expected_ready)),
        "false_negative_rate": _ratio(missed_ready, len(expected_ready)),
        "review_usefulness": _ratio(sum(row["expected"] == "review" for row in predicted_review), len(predicted_review)),
        "exclusion_accuracy": _ratio(sum(row["predicted"] == "excluded" for row in expected_excluded), len(expected_excluded)),
        "explanation_consistency": _ratio(explanation_consistent, len(rows)),
        "unsafe_ready_count": unsafe_ready,
        "case_count": len(rows),
    }
    gates = {
        "ready_precision": metrics["ready_precision"] >= 0.95,
        "precision_at_5": metrics["precision_at_5"] >= 0.80,
        "precision_at_10": metrics["precision_at_10"] >= 0.70,
        "surface_recall": metrics["surface_recall"] >= 0.80,
        "false_positive_rate": metrics["false_positive_rate"] <= 0.10,
        "false_negative_rate": metrics["false_negative_rate"] <= 0.20,
        "review_usefulness": metrics["review_usefulness"] >= 0.70,
        "exclusion_accuracy": metrics["exclusion_accuracy"] >= 0.90,
        "explanation_consistency": metrics["explanation_consistency"] >= 0.95,
        "unsafe_ready_count": unsafe_ready == 0,
    }
    return {"ok": not missing and all(gates.values()), "metrics": metrics, "gates": gates, "missing_predictions": missing, "rows": rows}
