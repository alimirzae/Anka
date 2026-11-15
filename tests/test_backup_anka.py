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
        self.assertEqual((backup / "epubs" / "sample.epub").read_bytes(), payload)

    def test_online_backup_includes_uncheckpointed_wal_transactions(self):
        db = self.create_db()
        writer = sqlite3.connect(db, timeout=30)
        try:
            self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower(), "wal")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("INSERT INTO books VALUES (?)", ("WAL-only edition",))
            writer.commit()
            self.assertTrue(Path(str(db) + "-wal").exists())
            result = self.run_backup()
            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list(self.output.glob("anka-*"))
            self.assertEqual(len(backups), 1)
            with sqlite3.connect(backups[0] / "anka.db") as restored:
                titles = {row[0] for row in restored.execute("SELECT title FROM books")}
                self.assertEqual(titles, {"Original EPUB", "WAL-only edition"})
                self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            writer.close()

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

    def test_backup_destination_cannot_be_application_parent(self):
        """Backups beside app binaries could be exposed by IIS or deployment."""
        db = self.create_db()
        before = db.read_bytes()
        result = self.run_backup(self.site)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("outside", result.stderr.lower())
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(list(self.site.glob("anka-*")), [])

    def test_backup_destination_cannot_be_app_data(self):
        """Never create a backup inside the live SQLite/EPUB directory."""
        db = self.create_db()
        before = db.read_bytes()
        result = self.run_backup(self.data)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(list(self.data.glob("anka-*")), [])

    def test_epub_inventory_failure_removes_incomplete_backup(self):
        """A rejected EPUB symlink must not leave a seemingly usable backup."""
        db = self.create_db()
        epubs = self.data / "epubs"
        epubs.mkdir()
        original = self.root / "external.epub"
        original.write_bytes(b"external-test-content")
        link = epubs / "linked.epub"
        try:
            link.symlink_to(original)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Creating symlinks is unavailable on this runner: " + str(exc))
        before = db.read_bytes()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(list(self.output.glob("anka-*")), [])
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(original.read_bytes(), b"external-test-content")

    def test_symlinked_epub_root_is_rejected_without_backup_artifacts(self):
        """A redirected EPUB root must not be accepted as a complete inventory."""
        db = self.create_db()
        external = self.root / "external-epubs"
        external.mkdir()
        payload = b"external-edition"
        (external / "external.epub").write_bytes(payload)
        try:
            (self.data / "epubs").symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Directory symlinks unavailable: " + str(exc))
        before = db.read_bytes()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(list(self.output.glob("anka-*")), [])
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual((external / "external.epub").read_bytes(), payload)

    def test_nested_epub_directory_symlink_is_rejected(self):
        """Nested directory links must not escape the EPUB inventory boundary."""
        db = self.create_db()
        epubs = self.data / "epubs"
        epubs.mkdir()
        external = self.root / "outside"
        external.mkdir()
        original = external / "private.epub"
        payload = b"outside-fixture"
        original.write_bytes(payload)
        try:
            (epubs / "redirect").symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Directory symlinks unavailable: " + str(exc))
        before = db.read_bytes()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(list(self.output.glob("anka-*")), [])
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(original.read_bytes(), payload)

    def test_epub_root_file_is_rejected_without_backup_artifacts(self):
        """An EPUB inventory path that is a file must fail closed."""
        db = self.create_db()
        root_file = self.data / "epubs"
        payload = b"not-a-directory"
        root_file.write_bytes(payload)
        before = db.read_bytes()
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("directory", result.stderr.lower())
        self.assertEqual(list(self.output.glob("anka-*")), [])
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(root_file.read_bytes(), payload)

    def test_corrupt_database_is_rejected_without_backup_artifacts(self):
        """A damaged source must never produce a valid-looking backup."""
        db = self.data / "anka.db"
        damaged = b"not a sqlite database; isolated test fixture"
        db.write_bytes(damaged)
        result = self.run_backup()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(db.read_bytes(), damaged)
        self.assertEqual(list(self.output.glob("anka-*")), [])
        self.assertFalse((self.data / "anka.db.partial").exists())

    def test_database_is_not_modified(self):
        db = self.create_db()
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
