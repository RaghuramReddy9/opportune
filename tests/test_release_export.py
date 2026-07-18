from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.release.export_candidate import export_candidate, validate_candidate


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseExportTests(unittest.TestCase):
    def test_allowlist_export_contains_public_product_and_excludes_private_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "opportune"
            result = export_candidate(PROJECT_ROOT, destination)

            self.assertGreater(result.file_count, 0)
            self.assertTrue((destination / "README.md").is_file())
            self.assertTrue((destination / ".github/workflows/ci.yml").is_file())
            self.assertTrue((destination / "onboarding/service.py").is_file())
            self.assertTrue((destination / "data/skill_taxonomy.yaml").is_file())
            self.assertTrue((destination / "profile/availability.yaml").is_file())
            self.assertTrue((destination / "profile/skills.example.yaml").is_file())
            self.assertTrue((destination / "frontend/dist/index.html").is_file())
            self.assertTrue((destination / "assets/screenshots/dashboard.png").is_file())
            self.assertTrue((destination / "desktop_launcher.py").is_file())
            self.assertTrue((destination / "profile_context.py").is_file())
            self.assertTrue((destination / "pilot_metrics.py").is_file())
            self.assertTrue((destination / "benchmarks/report.py").is_file())
            self.assertTrue((destination / "scripts/smoke_installed.py").is_file())
            self.assertTrue((destination / "RELEASE_SCORECARD.md").is_file())

            for forbidden in (
                "tracker",
                "logs",
                "config.yaml",
                ".env",
                ".hermes",
                ".kilo",
                ".memory",
                ".venv",
                "frontend/node_modules",
                "dashboard/job_hunt_command_center.html",
                "dashboard/ready_jobs.json",
                "mail_monitor",
                "evidence",
                "outreach",
                "reporting",
            ):
                self.assertFalse((destination / forbidden).exists(), forbidden)

            validate_candidate(destination)

    def test_existing_destination_requires_explicit_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "opportune"
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                export_candidate(PROJECT_ROOT, destination)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
