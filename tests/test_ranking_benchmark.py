from unittest.mock import patch

from ranking.benchmark import evaluate


def test_v1_ranking_quality_gates_pass():
    report = evaluate()
    assert report["ok"], report["errors"]
    assert report["metrics"]["unsafe_false_applies"] == 0


def test_quality_gate_is_independent_of_local_user_profile():
    incompatible_preferences = {
        "target_levels": ["mid_level"],
        "secondary_levels": [],
        "visa_policy": "none",
    }
    with (
        patch(
            "config.get_profile_config",
            return_value={"locations": ["London"], "target_levels": ["mid_level"]},
        ),
        patch(
            "resume.resume_profile.load_candidate_preferences",
            return_value=incompatible_preferences,
        ),
        patch(
            "ranking.score.load_candidate_preferences",
            return_value=incompatible_preferences,
        ),
    ):
        report = evaluate()

    assert report["ok"], report["errors"]
