"""Public-v1 onboarding/config/privacy API tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.asgi_client import ASGITestClient as TestClient

import dashapi.server as server
from dashboard.db import connect, init_db, set_db_path, upsert_scraped_job


class PublicV1APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "dashboard.db"
        init_db(self.db_path)
        set_db_path(self.db_path)
        self.client = TestClient(server.app)

    def tearDown(self):
        set_db_path(None)
        self.tmp.cleanup()

    def test_config_round_trip(self):
        payload = {"app": {"name": "Test"}, "profile": {"timeline": {"max_age_days": 3}}, "sources": []}
        with patch("public_ops.cfg.CONFIG_PATH", self.tmp_path / "config.yaml"):
            resp = self.client.post("/api/config", json={"config": payload})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["ok"])
            got = self.client.get("/api/config")
            self.assertEqual(got.json()["config"]["profile"]["timeline"]["max_age_days"], 3)

    def test_config_validation_rejects_invalid_timeline(self):
        from public_ops import save_config

        with patch("public_ops.cfg.CONFIG_PATH", self.tmp_path / "config.yaml"):
            with self.assertRaisesRegex(ValueError, "max_age_days"):
                save_config({"profile": {"timeline": {"max_age_days": 365}}, "sources": []})

    def test_legacy_resume_profile_route_is_removed(self):
        self.assertNotIn("/api/profile/resume", server.app.openapi()["paths"])

    def test_dashboard_hides_demo_cards_once_real_jobs_exist(self):
        self.client.post("/api/demo?clear_first=true")
        with connect(self.db_path) as conn:
            upsert_scraped_job(conn, {
                "company": "RealCo",
                "title": "Applied AI Engineer",
                "apply_url": "https://example.org/real-role",
                "source": "greenhouse",
                "action_tag": "watch",
            })
        dash = self.client.get("/api/dashboard").json()
        visible = [job for bucket in dash["buckets"].values() for job in bucket]
        self.assertEqual([job["company"] for job in visible], ["RealCo"])
        self.assertEqual(dash["stats"]["total"], 1)

    def test_demo_and_privacy_wipe(self):
        seeded = self.client.post("/api/demo?clear_first=true")
        self.assertEqual(seeded.status_code, 200)
        self.assertEqual(seeded.json()["inserted"], 3)
        dash = self.client.get("/api/dashboard").json()
        self.assertEqual(dash["stats"]["total"], 0)
        visible_jobs = [job for bucket in dash["buckets"].values() for job in bucket]
        self.assertEqual(len(visible_jobs), 3)
        self.assertTrue(all(job["is_demo"] for job in visible_jobs))
        denied = self.client.post("/api/privacy/wipe", json={"confirm": "no"})
        self.assertEqual(denied.status_code, 400)
        wiped = self.client.post("/api/privacy/wipe", json={"confirm": "WIPE"})
        self.assertEqual(wiped.status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard").json()["stats"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
