#!/usr/bin/env python3
"""Read-only verifier regression tests using disposable SQLite and EPUB fixtures."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify-anka-backup.py"

class VerifyBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "backup"
        self.root.mkdir()
        self.db = self.root / "anka.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE editions (title TEXT)")
            conn.execute("INSERT INTO editions VALUES ('fixture')")
        self.epub = self.root / "epubs" / "sample.epub"
        self.epub.parent.mkdir()
        self.epub.write_bytes(b"epub-fixture")
        self.manifest = {
            "database": {"name": "anka.db", "sha256": self.hash(self.db)},
            "epubs": [{"path": "epubs/sample.epub", "size": self.epub.stat().st_size,
                       "sha256": self.hash(self.epub)}],
        }
        self.save_manifest()

    @staticmethod
    def hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def verify(self):
        return subprocess.run([sys.executable, str(SCRIPT), "--backup-dir", str(self.root)],
                              capture_output=True, text=True, timeout=30)

    def test_valid_snapshot_passes_without_writing(self):
        before = {p.relative_to(self.root).as_posix(): self.hash(p)
                  for p in self.root.rglob("*") if p.is_file()}
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {p.relative_to(self.root).as_posix(): self.hash(p)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_modified_epub_fails(self):
        self.epub.write_bytes(b"tampered")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_modified_database_fails(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO editions VALUES ('tampered')")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_missing_epub_fails(self):
        self.epub.unlink()
        self.assertNotEqual(self.verify().returncode, 0)

    def test_unlisted_epub_fails(self):
        (self.epub.parent / "extra.epub").write_bytes(b"extra")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_duplicate_epub_manifest_entry_fails(self):
        self.manifest["epubs"].append(dict(self.manifest["epubs"][0]))
        self.save_manifest()
        self.assertNotEqual(self.verify().returncode, 0)

    def test_parent_traversal_fails(self):
        self.manifest["epubs"][0]["path"] = "epubs/../sample.epub"
        self.save_manifest()
        self.assertNotEqual(self.verify().returncode, 0)

    def test_redirected_epub_fails(self):
        outside = Path(self.tmp.name) / "outside.epub"
        outside.write_bytes(b"epub-fixture")
        self.epub.unlink()
        try:
            self.epub.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Symlinks unavailable: " + str(exc))
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertEqual(outside.read_bytes(), b"epub-fixture")

if __name__ == "__main__":
    unittest.main()
