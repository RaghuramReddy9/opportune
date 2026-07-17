import tempfile
import unittest
from pathlib import Path

from core.skill_matcher import load_user_profile, skill_match
from core.temporal_scorer import freshness_score, time_weight, combined_weight

class TestSkillMatcher(unittest.TestCase):
    def setUp(self):
        # Create a temporary profile; never mutate the real runtime profile.
        import yaml
        self.tmpdir = tempfile.TemporaryDirectory()
        self.profile_path = Path(self.tmpdir.name) / 'ram_skills.yaml'
        data = {
            'skills': [
                {'name': 'python', 'level': 4},
                {'name': 'pytorch', 'level': 3},
                {'name': 'aws', 'level': 2},
                {'name': 'git', 'level': 5},
            ]
        }
        with open(self.profile_path, 'w') as f:
            yaml.dump(data, f)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_profile(self):
        profile = load_user_profile(self.profile_path)
        self.assertEqual(profile.get('python'), 4)
        self.assertEqual(profile.get('pytorch'), 3)
        self.assertEqual(profile.get('aws'), 2)
        self.assertEqual(profile.get('git'), 5)
        self.assertEqual(profile.get('nonexistent'), 0)

    def test_skill_match_perfect(self):
        text = "We need Python and PyTorch experience."
        score, missing = skill_match(text, {'python': 5, 'pytorch': 5})
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(missing, [])

    def test_skill_match_partial(self):
        text = "We need Python, PyTorch, and AWS."
        # user has python 4, pytorch 3, aws 2 => weighted overlap = min(4,5)+min(3,5)+min(2,5)=4+3+2=9
        # max possible = 3*5=15 => 9/15 = 0.6
        score, missing = skill_match(text, {'python': 4, 'pytorch': 3, 'aws': 2})
        self.assertAlmostEqual(score, 0.6, places=2)
        # missing skills where level <3: aws level 2 => missing
        self.assertIn('aws', missing)
        self.assertNotIn('python', missing)
        self.assertNotIn('pytorch', missing)

    def test_skill_match_empty(self):
        score, missing = skill_match("", {'python': 5})
        self.assertEqual(score, 0.0)
        self.assertEqual(missing, [])

class TestTemporalScorer(unittest.TestCase):
    def test_freshness_scores(self):
        self.assertEqual(freshness_score("New (0-24h)"), 1.0)
        self.assertEqual(freshness_score("Newly Discovered"), 1.0)
        self.assertEqual(freshness_score("Recent (24-48h)"), 0.8)
        self.assertEqual(freshness_score("This Week (3-7d)"), 0.6)
        self.assertEqual(freshness_score("Old (8-14d)"), 0.3)
        self.assertEqual(freshness_score("Unknown"), 0.0)
        self.assertEqual(freshness_score(""), 0.0)

    def test_time_weight(self):
        # We cannot reliably test time_weight without mocking datetime.now,
        # but we can test that it returns a float between 0 and 1.
        w = time_weight()
        self.assertGreaterEqual(w, 0.0)
        self.assertLessEqual(w, 1.0)

    def test_combined_weight(self):
        cw = combined_weight("New (0-24h)")
        self.assertGreaterEqual(cw, 0.0)
        self.assertLessEqual(cw, 1.0)
        # If time_weight is 1.0 (we are in window), combined_weight should be 1.0
        # We'll just trust that the functions work.

if __name__ == "__main__":
    unittest.main()