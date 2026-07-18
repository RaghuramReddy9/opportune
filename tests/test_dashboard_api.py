"""RED tests for the FastAPI dashboard API."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.asgi_client import ASGITestClient as TestClient

import dashapi.server as server
from dashboard.db import create_profile, init_db, upsert_scraped_job, set_db_path


class DashboardAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_dash.db"
        init_db(self.db_path)
        set_db_path(self.db_path)
        self.client = TestClient(server.app)

    def tearDown(self):
        set_db_path(None)
        self.tmp.cleanup()

    def _sample_job(self, **overrides):
        job = {
            "company": "Stripe",
            "title": "Applied AI Engineer, New Grad",
            "location": "New York, NY",
            "apply_url": "https://stripe.com/jobs/123",
            "source": "greenhouse",
            "ats_type": "greenhouse",
            "resume_match_score": 95,
            "freshness": "New (0-24h)",
            "freshness_trust": "confirmed_posted_date",
            "action_tag": "apply_now",
            "target_role_families": ["applied_ai"],
            "matched_keywords": ["rag", "llm"],
            "why_matches": "Strong fit",
            "why_risky": "",
            "opt_signal": "Strong",
            "best_matching_project": "Multi-Agent RAG Pipeline",
        }
        job.update(overrides)
        return job

    def _approve_profile(self):
        create_profile(
            "Test Candidate",
            "Applied AI Engineer with Python and RAG experience.",
            '{"roles":["Applied AI Engineer"],"locations":["United States"]}',
            db_path=self.db_path,
        )

    def test_health_ok(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_update_status_uses_safe_release_checker(self):
        expected = {
            "ok": True,
            "checked": True,
            "current_version": "0.1.1",
            "latest_version": "0.1.2",
            "update_available": True,
            "release_url": "https://github.com/RaghuramReddy9/opportune/releases/tag/v0.1.2",
        }
        with patch("dashapi.server.check_for_updates", return_value=expected):
            resp = self.client.get("/api/update")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), expected)

    def test_cross_origin_mutation_is_rejected(self):
        resp = self.client.post(
            "/api/demo",
            headers={"Origin": "https://attacker.example"},
        )

        self.assertEqual(resp.status_code, 403)

    def test_different_local_port_mutation_is_rejected(self):
        resp = self.client.post(
            "/api/demo",
            headers={"Origin": "http://127.0.0.1:3000"},
        )

        self.assertEqual(resp.status_code, 403)

    def test_same_local_origin_mutation_is_allowed(self):
        client = TestClient(server.app, base_url="http://localhost:8770")

        resp = client.post(
            "/api/demo",
            headers={"Origin": "http://localhost:8770"},
        )

        self.assertEqual(resp.status_code, 200)

    def test_health_redacts_source_error_query_secrets(self):
        raw_key = "super-secret-key"
        source_health = {
            "sources": {
                "api_serpapi": {
                    "status": "circuit_open",
                    "last_error": f"GET https://serpapi.com/search.json?q=ai&api_key={raw_key}&num=10",
                    "nested": [f"https://example.com/path?access_token={raw_key}"],
                }
            }
        }
        with patch("dashapi.server.load_health", return_value=source_health):
            resp = self.client.get("/api/health")

        self.assertEqual(resp.status_code, 200)
        text = resp.text
        self.assertNotIn(raw_key, text)
        self.assertEqual(resp.json()["source_health"]["sources"]["api_serpapi"]["last_error"], "[redacted]")
        self.assertIn("access_token=[redacted]", text)

    def test_serves_built_frontend_assets_with_real_static_file(self):
        dist = Path(self.tmp.name) / "dist"
        assets = dist / "assets"
        assets.mkdir(parents=True)
        (dist / "index.html").write_text(
            '<div id="root"></div><script type="module" src="/assets/app.js"></script>'
        )
        (assets / "app.js").write_text("console.log('dashboard loaded')")
        old_frontend_dir = server.FRONTEND_DIR
        try:
            server.FRONTEND_DIR = dist
            resp = self.client.get("/assets/app.js")
        finally:
            server.FRONTEND_DIR = old_frontend_dir

        self.assertEqual(resp.status_code, 200)
        self.assertIn("dashboard loaded", resp.text)
        self.assertIn("javascript", resp.headers["content-type"])

    def test_installed_frontend_path_is_used_when_project_build_is_absent(self):
        missing_project = Path(self.tmp.name) / "missing-project-dist"
        installed = Path(self.tmp.name) / "installed-dist"
        installed.mkdir()
        (installed / "index.html").write_text("installed")

        resolved = server._resolve_frontend_dir(missing_project, installed)

        self.assertEqual(resolved, installed)

    def test_dashboard_empty_initially(self):
        resp = self.client.get("/api/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["stats"]["total"], 0)

    def test_set_status_moves_to_active_pipeline(self):
        from dashboard.db import connect

        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
        resp = self.client.post(f"/api/jobs/{uid}/status", json={"status": "applied"})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/dashboard")
        data = resp.json()
        self.assertEqual(data["stats"]["active_pipeline"], 1)

    def test_set_status_invalid_rejected(self):
        from dashboard.db import connect

        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
        resp = self.client.post(f"/api/jobs/{uid}/status", json={"status": "bogus"})
        self.assertEqual(resp.status_code, 400)

    def test_set_status_unknown_job_404(self):
        resp = self.client.post(
            "/api/jobs/unknown|job|00000000/status", json={"status": "applied"}
        )
        self.assertEqual(resp.status_code, 404)

    def test_set_note(self):
        from dashboard.db import connect

        with connect(self.db_path) as conn:
            uid = upsert_scraped_job(conn, self._sample_job())
        resp = self.client.post(f"/api/jobs/{uid}/note", json={"note": "Referred by Alex"})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/jobs?status=discovered")
        jobs = resp.json()
        self.assertEqual(jobs[0]["note"], "Referred by Alex")

    def test_list_jobs_filters(self):
        from dashboard.db import connect

        with connect(self.db_path) as conn:
            upsert_scraped_job(conn, self._sample_job())
            upsert_scraped_job(
                conn, self._sample_job(company="Brex", title="AI Engineer 2", action_tag="watch")
            )
        resp = self.client.get("/api/jobs?action_tag=apply_now")
        self.assertEqual(len(resp.json()), 1)


    def test_scrape_api_does_not_store_excluded_jobs(self):
        from dashboard.db import list_jobs

        self._approve_profile()

        fake_result = {
            "raw_count": 2,
            "dashboard_jobs": [
                self._sample_job(company="KeptCo", title="Applied AI Engineer", action_tag="apply_now"),
                self._sample_job(
                    company="SkipCo",
                    title="AI Engineer Requiring Citizenship",
                    action_tag="skip",
                    eligibility_reason_codes=["citizenship_or_clearance"],
                ),
            ],
        }
        with patch("dashapi.server.scrape_all", return_value=fake_result):
            resp = self.client.post("/api/scrape?dry_run=false")
        self.assertEqual(resp.status_code, 200)
        with server.connect(self.db_path) as conn:
            stored = list_jobs(conn)
        stored_companies = [j["company"] for j in stored]
        self.assertIn("KeptCo", stored_companies)
        self.assertNotIn("SkipCo", stored_companies)

    def test_scrape_api_dry_run_does_not_store_jobs(self):
        from dashboard.db import list_jobs

        self._approve_profile()

        fake_result = {
            "raw_count": 1,
            "dashboard_jobs": [self._sample_job(company="DryRunCo")],
        }
        with patch("dashapi.server.scrape_all", return_value=fake_result):
            resp = self.client.post("/api/scrape?dry_run=true")

        self.assertEqual(resp.status_code, 200)
        with server.connect(self.db_path) as conn:
            self.assertEqual(list_jobs(conn), [])

    def test_sync_demotes_existing_job_when_fresh_enrichment_excludes_it(self):
        from dashboard.db import list_jobs

        existing = self._sample_job(
            company="Scale AI",
            title=" Machine Learning Research Engineer",
            action_tag="watch",
            apply_url="https://jobs.example.com/scale-old",
        )
        excluded = self._sample_job(
            company=" Scale AI ",
            title="Machine Learning Research Engineer ",
            action_tag="skip",
            apply_url="https://jobs.example.com/scale-new",
            eligibility_reason_codes=["experience_over_two_years"],
        )
        with server.connect(self.db_path) as conn:
            upsert_scraped_job(conn, existing, check_links=False)
            server._sync_dashboard_jobs(conn, [excluded])

        with server.connect(self.db_path) as conn:
            stored = list_jobs(conn)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["action_tag"], "skip")

    def test_smart_scrape_api_does_not_store_excluded_jobs(self):
        from dashboard.db import list_jobs

        self._approve_profile()

        fake_result = {
            "raw_count": 2,
            "windows_run": ["morning"],
            "high_apply_windows": 1,
            "stopped_reason": "enough",
            "dashboard_jobs": [
                self._sample_job(company="KeptCo", title="Applied AI Engineer", action_tag="apply_now"),
                self._sample_job(
                    company="SkipCo",
                    title="AI Engineer No Sponsorship",
                    action_tag="skip",
                    eligibility_reason_codes=["visa_or_opt_risk"],
                ),
            ],
        }
        with patch("dashapi.server.smart_scrape", return_value=fake_result):
            resp = self.client.post("/api/smart-scrape", json={"live": True, "min_high": 1})
        self.assertEqual(resp.status_code, 200)
        with server.connect(self.db_path) as conn:
            stored = list_jobs(conn)
        stored_companies = [j["company"] for j in stored]
        self.assertIn("KeptCo", stored_companies)
        self.assertNotIn("SkipCo", stored_companies)

    def test_smart_scrape_api_non_live_does_not_store_jobs(self):
        from dashboard.db import list_jobs

        self._approve_profile()

        fake_result = {
            "raw_count": 1,
            "windows_run": ["morning"],
            "high_apply_windows": 1,
            "stopped_reason": "enough",
            "dashboard_jobs": [self._sample_job(company="DrySmartCo")],
        }
        with patch("dashapi.server.smart_scrape", return_value=fake_result):
            resp = self.client.post("/api/smart-scrape?live=false&min_high=1")

        self.assertEqual(resp.status_code, 200)
        with server.connect(self.db_path) as conn:
            self.assertEqual(list_jobs(conn), [])

    def test_sync_dashboard_jobs_verifies_links_for_non_demo(self):
        from dashboard.db import list_jobs

        captured = {}

        def fake_verify(url, *, timeout=12):
            captured["url"] = url
            return {"ok": True, "link_status": "ok", "checked_at": "2026-07-11T00:00:00Z"}

        jobs = [
            self._sample_job(company="LinkCo", title="Applied AI Engineer", action_tag="apply_now"),
            self._sample_job(company="DemoCo", title="Sample", action_tag="watch", is_demo=True,
                            apply_url="https://example.com/sample"),
        ]
        with patch("core.link_check.verify_job_link", side_effect=fake_verify):
            with server.connect(self.db_path) as conn:
                server._sync_dashboard_jobs(conn, jobs)
        # Non-demo job link was verified; demo was skipped.
        self.assertEqual(captured["url"], "https://stripe.com/jobs/123")
        with server.connect(self.db_path) as conn:
            stored = {j["company"]: j for j in list_jobs(conn)}
        self.assertEqual(stored["LinkCo"]["link_status"], "ok")
        self.assertEqual(stored["LinkCo"]["link_verified_at"], "2026-07-11T00:00:00Z")
        self.assertEqual(stored["DemoCo"]["link_status"], "placeholder")


if __name__ == "__main__":
    unittest.main()
