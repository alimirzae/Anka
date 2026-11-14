#!/usr/bin/env python3
"""Isolated regression checks for ANKA's online SQLite backup.

Run: python -m unittest discover -s tests -p 'test_backup_anka.py'
Only temporary fixtures are used; production SQLite/EPUB files are never touched.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup-anka.py"


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = self.root / "site"
        self.data = self.site / "App_Data"
        self.data.mkdir(parents=True)
        self.output = self.root / "backups"

    def run_backup(self, output=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--data-dir", str(self.data),
             "--output-dir", str(output or self.output)],
            text=True, capture_output=True, timeout=45,
        )

    def create_db(self):
        db = self.data / "anka.db"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE books (title TEXT NOT NULL)")
            conn.execute("INSERT INTO books VALUES (?)", ("Original EPUB",))
        return db

    def test_backup_integrity_and_epub_inventory(self):
        source_db = self.create_db()
        epub = self.data / "epubs" / "sample.epub"
        epub.parent.mkdir()
        payload = b"isolated-fixture-not-a-real-epub"
        epub.write_bytes(payload)
        result = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list(self.output.glob("anka-*"))
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        with sqlite3.connect(backup / "anka.db") as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("SELECT title FROM books").fetchone()[0], "Original EPUB")
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["database"]["sha256"],
                         hashlib.sha256((backup / "anka.db").read_bytes()).hexdigest())
        self.assertEqual(manifest["epubs"], [{
            "path": "epubs/sample.epub", "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }])
        self.assertEqual(source_db.exists(), True)
        self.assertEqual(epub.read_bytes(), payload)
        self.assertFalse((backup / "epubs").exists())

    def test_missing_database_is_rejected_without_creating_one(self):
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.data / "anka.db").exists())
        self.assertFalse(self.output.exists())

    def test_destination_inside_application_is_rejected(self):
        self.create_db()
        result = self.run_backup(self.site / "backups")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.site / "backups").exists())

    def test_database_is_not_modified(self):
        db = self.create_db()
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
