"""Security regression tests for backup file permissions and cleanup.

Uses disposable SQLite fixtures only; never reads production assets.
"""
import os
import sqlite3
from contextlib import closing
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_sqlite.py"


class BackupPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        root = Path(self.workspace.name)
        self.live = root / "App_Data"
        self.backups = root / "backups"
        self.live.mkdir()
        self.backups.mkdir()
        self.source = self.live / "anka.db"
        self.destination = self.backups / "verified.db"
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("CREATE TABLE editions (id INTEGER PRIMARY KEY, title TEXT)")
            db.execute("INSERT INTO editions VALUES (1, 'safe')")
            db.commit()

    def run_backup(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source", str(self.source),
             "--destination", str(self.destination)],
            capture_output=True, text=True, timeout=30,
        )

    def test_verified_backup_is_private_on_posix(self):
        if os.name == "nt":
            self.skipTest("Windows file privacy depends on destination NTFS ACLs")
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.destination.stat().st_mode & 0o077, 0)
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(db.execute("SELECT title FROM editions").fetchone()[0], "safe")

    def test_failed_backup_does_not_leave_temporary_files(self):
        self.source.write_bytes(b"corrupted sqlite source")
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.backups.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
