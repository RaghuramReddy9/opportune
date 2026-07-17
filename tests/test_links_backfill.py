"""Tests for `jobhunt links backfill` link-verification backfill command."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class LinksBackfillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "dash.db"
        from dashboard import db as dbmod

        dbmod.set_db_path(self.db_path)
        dbmod.init_db(self.db_path)
        with dbmod.connect() as conn:
            self.uid_real = dbmod.upsert_scraped_job(
                conn,
                {
                    "company": "RealCo",
                    "title": "Applied AI Engineer",
                    "apply_url": "https://real.example.com/job/1",
                    "source": "greenhouse",
                    "action_tag": "watch",
                },
            )
            self.uid_demo = dbmod.upsert_scraped_job(
                conn,
                {
                    "company": "DemoCo",
                    "title": "Sample Role",
                    "apply_url": "https://example.com/sample",
                    "source": "sample_data",
                    "is_demo": True,
                    "action_tag": "watch",
                },
            )
            # Force the real row to look stale (no verified date).
            conn.execute(
                "UPDATE jobs SET link_verified_at = '' WHERE job_uid = ?",
                (self.uid_real,),
            )
            conn.commit()

    def tearDown(self):
        from dashboard import db as dbmod

        dbmod.set_db_path(None)
        self.tmp.cleanup()

    def _run(self, fake_status):
        from jobhunt import build_parser, cmd_links

        captured = {}

        def fake_verify(url, *, timeout=12):
            captured["url"] = url
            return fake_status

        with patch("core.link_check.verify_job_link", side_effect=fake_verify):
            args = build_parser().parse_args(["links", "backfill", "--json"])
            cmd_links(args)
        return captured

    def test_backfill_marks_real_job_and_skips_demo(self):
        from dashboard import db as dbmod

        self._run(
            {"ok": True, "link_status": "ok", "checked_at": "2026-07-11T00:00:00Z"}
        )
        with dbmod.connect(self.db_path) as conn:
            real = dbmod.get_job(conn, self.uid_real)
            demo = dbmod.get_job(conn, self.uid_demo)
        self.assertEqual(real["link_status"], "ok")
        self.assertEqual(real["link_verified_at"], "2026-07-11T00:00:00Z")
        # Demo row must not be re-verified (still its seeded placeholder).
        self.assertEqual(demo["link_status"], "placeholder")
        self.assertEqual(demo["link_verified_at"], "")

    def test_backfill_persists_dead_status(self):
        from dashboard import db as dbmod

        self._run(
            {"ok": False, "link_status": "dead", "checked_at": "2026-07-11T01:00:00Z"}
        )
        with dbmod.connect(self.db_path) as conn:
            real = dbmod.get_job(conn, self.uid_real)
        self.assertEqual(real["link_status"], "dead")
        self.assertEqual(real["link_verified_at"], "2026-07-11T01:00:00Z")


if __name__ == "__main__":
    unittest.main()
