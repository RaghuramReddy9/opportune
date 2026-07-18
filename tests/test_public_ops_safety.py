"""Safety tests for configured storage, backup, and destructive local operations."""
from __future__ import annotations

import sqlite3
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import config
from dashboard import db
from public_ops import backup_local_state, export_data, restore_local_state, wipe_local_data


class PublicOpsSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "custom-name.db"
        db.set_db_path(self.db_path)
        db.init_db()

    def tearDown(self):
        db.set_db_path(None)
        self.tmp.cleanup()

    def _seed(self) -> None:
        with db.connect() as conn:
            db.upsert_scraped_job(
                conn,
                {
                    "company": "SafeCo",
                    "title": "AI Engineer",
                    "apply_url": "https://jobs.example.org/1",
                    "source": "greenhouse",
                },
                check_links=False,
            )

    def _job_count_in_backup(self, backup_path: Path) -> int:
        with zipfile.ZipFile(backup_path) as archive:
            self.assertIsNone(archive.testzip())
            member = f"tracker/{self.db_path.name}"
            restored_path = self.tmp_path / "restored.db"
            restored_path.write_bytes(archive.read(member))
        connection = sqlite3.connect(restored_path)
        try:
            return connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        finally:
            connection.close()

    def test_dashboard_uses_configured_database_path_by_default(self):
        self.assertEqual(db.DEFAULT_DB_PATH, config.DASHBOARD_DB_PATH)

    def test_backup_uses_consistent_sqlite_snapshot(self):
        self._seed()

        backup_path = backup_local_state()

        self.assertEqual(backup_path.parent, self.tmp_path / "backups")
        self.assertEqual(self._job_count_in_backup(backup_path), 1)
        self.assertEqual(stat.S_IMODE(backup_path.stat().st_mode), 0o600)

    def test_export_uses_configured_platform_export_directory(self):
        self._seed()
        export_dir = self.tmp_path / "exports"

        with patch("public_ops.cfg.EXPORT_DIR", export_dir):
            path = export_data()

        self.assertEqual(path.parent, export_dir)
        self.assertTrue(path.is_file())

    def test_wipe_backs_up_before_clearing_primary_database(self):
        self._seed()
        with db.connect() as conn:
            conn.execute("CREATE TABLE seen_jobs (id INTEGER PRIMARY KEY, url TEXT)")
            conn.execute("INSERT INTO seen_jobs (url) VALUES ('https://example.org/seen')")

        result = wipe_local_data("WIPE")

        backup_path = Path(result["backup_path"])
        self.assertTrue(self.db_path.exists())
        self.assertEqual(self._job_count_in_backup(backup_path), 1)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0], 0)

    def test_restore_validates_and_atomically_replaces_database(self):
        self._seed()
        backup_path = backup_local_state()
        with db.connect() as conn:
            conn.execute("DELETE FROM jobs")

        result = restore_local_state(backup_path, confirm="RESTORE")

        self.assertTrue(Path(result["pre_restore_backup_path"]).is_file())
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)

    def test_restore_rejects_unsafe_archive_members(self):
        archive_path = self.tmp_path / "unsafe.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("../dashboard.db", b"not sqlite")

        with self.assertRaisesRegex(ValueError, "unsafe"):
            restore_local_state(archive_path, confirm="RESTORE")


if __name__ == "__main__":
    unittest.main()
