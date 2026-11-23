"""Adversarial, disposable-fixture tests for the production SQLite backup CLI.

Never run against a production database or real EPUBs.
"""
import sqlite3
from contextlib import closing
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_sqlite.py"


class BackupAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.live = root / "App_Data"
        self.out = root / "backups"
        self.live.mkdir()
        self.out.mkdir()
        self.source = self.live / "anka.db"
        self.target = self.out / "snapshot.db"
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE editions (id INTEGER PRIMARY KEY, title TEXT)")
            db.execute("INSERT INTO editions VALUES (1, 'published')")
            db.commit()

    def run_cli(self, target=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source", str(self.source),
             "--destination", str(target or self.target)],
            capture_output=True, text=True, timeout=30,
        )

    def test_live_epub_is_not_modified_by_backup(self):
        epub = self.live / "original.epub"
        epub.write_bytes(b"real-epub-placeholder-untouched")
        before = epub.read_bytes()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(epub.read_bytes(), before)
        with closing(sqlite3.connect(self.target)) as db:
            self.assertEqual(db.execute("SELECT title FROM editions").fetchone()[0], "published")

    def test_corrupt_source_is_rejected_without_publishing_backup(self):
        self.source.write_bytes(b"not a sqlite database")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())

    def test_existing_destination_is_not_overwritten(self):
        self.target.write_bytes(b"keep existing snapshot")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), b"keep existing snapshot")


if __name__ == "__main__":
    unittest.main()
