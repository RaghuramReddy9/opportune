"""Tests for link liveness verification, demo separation, and aggregator demotion."""
from __future__ import annotations

import tempfile
import unittest
import socket
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from dashboard import db


def _make_job(**overrides) -> dict:
    base = {
        "company": "TestCo",
        "title": "AI Engineer",
        "location": "Remote US",
        "apply_url": "https://example.com/job/1",
        "source": "greenhouse",
        "ats_type": "greenhouse",
        "resume_match_score": 80,
        "freshness": "New (0-24h)",
        "action_tag": "watch",
        "matched_keywords": ["python"],
        "target_role_families": ["applied_ai"],
    }
    base.update(overrides)
    return base


class LinkCheckTests(unittest.TestCase):
    def test_private_network_url_is_rejected_without_request(self):
        from core.link_check import verify_job_link

        with patch("core.link_check._open_url") as request:
            status = verify_job_link("http://127.0.0.1:8000/admin")

        self.assertFalse(status["ok"])
        self.assertEqual(status["link_status"], "unsafe")
        request.assert_not_called()

    def test_hostname_resolving_to_private_network_is_rejected(self):
        from core.link_check import _is_safe_link_url

        private_resolution = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))
        ]
        with patch("core.http.socket.getaddrinfo", return_value=private_resolution):
            self.assertFalse(_is_safe_link_url("https://jobs.example.net/opening"))

    def test_placeholder_url_is_flagged_dead(self):
        from core.link_check import verify_job_link
        status = verify_job_link("https://example.com/jobs/rag-engineer")
        self.assertFalse(status["ok"])
        self.assertEqual(status["link_status"], "placeholder")

    @patch("core.link_check._open_url")
    def test_reachable_url_is_ok(self, mock_urlopen):
        from core.link_check import verify_job_link

        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "https://job-boards.greenhouse.io/scaleai/jobs/4625345005"
        response.__enter__.return_value = response
        mock_urlopen.return_value = response
        with patch("core.link_check._is_safe_link_url", return_value=True):
            status = verify_job_link("https://job-boards.greenhouse.io/scaleai/jobs/4625345005")
        self.assertTrue(status["ok"])
        self.assertEqual(status["link_status"], "ok")
        self.assertIn("checked_at", status)

    @patch("core.link_check._open_url")
    def test_head_failure_falls_back_to_get_and_marks_404_dead(self, mock_urlopen):
        from core.link_check import verify_job_link

        error = HTTPError("https://jobs.example.net/closed", 404, "Not Found", Message(), None)
        mock_urlopen.side_effect = [error, error]
        with patch("core.link_check._is_safe_link_url", return_value=True):
            status = verify_job_link("https://jobs.example.net/closed")
        self.assertFalse(status["ok"])
        self.assertEqual(status["link_status"], "dead")
        self.assertEqual(mock_urlopen.call_count, 2)

    def test_inconclusive_http_errors_are_not_marked_dead(self):
        from core.link_check import verify_job_link

        for code in (401, 403, 429, 500, 503):
            with self.subTest(code=code), patch("core.link_check._open_url") as mock_urlopen, patch(
                "core.link_check._is_safe_link_url", return_value=True
            ):
                error = HTTPError("https://jobs.example.net/opening", code, "Unavailable", Message(), None)
                mock_urlopen.side_effect = [error, error]

                status = verify_job_link("https://jobs.example.net/opening")

                self.assertFalse(status["ok"])
                self.assertEqual(status["link_status"], "inconclusive")
                self.assertEqual(mock_urlopen.call_count, 2)

    def test_redirect_handler_rejects_private_destination_before_following(self):
        from core.link_check import UnsafeRedirectError, _SafeRedirectHandler

        handler = _SafeRedirectHandler()
        with patch("core.link_check._is_safe_link_url", return_value=False), self.assertRaises(
            UnsafeRedirectError
        ):
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                Message(),
                "http://127.0.0.1/admin",
            )

    @patch("core.link_check._open_url")
    def test_final_redirect_url_is_revalidated(self, mock_open):
        from core.link_check import verify_job_link

        response = MagicMock()
        response.status = 200
        response.geturl.return_value = "http://127.0.0.1/admin"
        response.__enter__.return_value = response
        mock_open.return_value = response
        with patch(
            "core.link_check._is_safe_link_url",
            side_effect=lambda value: not value.startswith("http://127."),
        ):
            status = verify_job_link("https://jobs.example.net/opening")

        self.assertFalse(status["ok"])
        self.assertEqual(status["link_status"], "unsafe")


class DemoSeparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "dashboard.db"
        db.set_db_path(self.db_path)
        db.init_db(self.db_path)

    def tearDown(self):
        db.set_db_path(None)
        self.tmp.cleanup()

    def test_sample_data_is_flagged_demo_and_excluded_from_default_model(self):
        with db.connect(self.db_path) as conn:
            db.upsert_scraped_job(conn, _make_job(source="sample_data", apply_url="https://example.com/x"))
            db.upsert_scraped_job(conn, _make_job(company="RealCo", source="greenhouse"))
            model = db.get_dashboard_model(conn)
        all_jobs = [j for b in model["buckets"].values() for j in b]
        # Default model must not surface demo rows as real results.
        self.assertFalse(any(j.get("is_demo") for j in all_jobs))
        # The real (non-demo) job must still be present.
        self.assertTrue(any(j["company"] == "RealCo" for j in all_jobs))

    def test_demo_count_exposed_when_requested(self):
        with db.connect(self.db_path) as conn:
            db.upsert_scraped_job(conn, _make_job(source="sample_data", apply_url="https://example.com/x"))
            db.upsert_scraped_job(conn, _make_job(company="RealCo", source="greenhouse"))
            model = db.get_dashboard_model(conn, include_demo=True)
        demo_jobs = [j for b in model["buckets"].values() for j in b if j.get("is_demo")]
        self.assertEqual(len(demo_jobs), 1)
        # Demo cards render, but dashboard totals only count real scraped jobs.
        self.assertEqual(model["stats"]["total"], 1)


class AggregatorDemotionTests(unittest.TestCase):
    def test_aggregator_source_lowers_apply_window_score(self):
        from ranking.apply_window import score_apply_window
        normal = score_apply_window(_make_job(source="greenhouse", ats_type="greenhouse", apply_url="https://greenhouse.io/x"))
        agg = score_apply_window(_make_job(source="api_serpapi", ats_type="serpapi", apply_url="https://lensa.com/job/1"))
        self.assertLess(agg["apply_window_score"], normal["apply_window_score"])
        self.assertIn("aggregator", " ".join(agg["apply_window_reasons"]).lower())


if __name__ == "__main__":
    unittest.main()
