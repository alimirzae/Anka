#!/usr/bin/env python3
"""Read-only verifier regression tests using disposable SQLite and EPUB fixtures."""
import hashlib
from contextlib import closing
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
        with closing(sqlite3.connect(self.db)) as conn:
            with conn:
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

    def test_backup_directory_with_uri_delimiters_is_readable(self):
        # SQLite URI paths must encode # and ? rather than treating them
        # as fragments or query parameters. Use only disposable fixtures.
        # Windows forbids ? in directory names; # remains a valid URI delimiter
        # regression there. POSIX additionally exercises literal ? encoding.
        folder_name = "backup # rights edition" if sys.platform == "win32" else "backup # rights? edition"
        renamed = self.root.with_name(folder_name)
        self.root.rename(renamed)
        self.root = renamed
        self.db = renamed / "anka.db"
        self.epub = renamed / "epubs" / "sample.epub"
        before_db = self.hash(self.db)
        before_epub = self.hash(self.epub)
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.hash(self.db), before_db)
        self.assertEqual(self.hash(self.epub), before_epub)
        self.assertFalse((self.root / "anka.db-wal").exists())
        self.assertFalse((self.root / "anka.db-shm").exists())

    def test_modified_epub_fails(self):
        self.epub.write_bytes(b"tampered")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_modified_database_fails(self):
        with closing(sqlite3.connect(self.db)) as conn:
            with conn:
                conn.execute("INSERT INTO editions VALUES ('tampered')")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_corrupt_sqlite_with_matching_hash_fails_integrity_check(self):
        # A valid digest proves identity, not that the SQLite file is usable.
        original_epub = self.hash(self.epub)
        self.db.write_bytes(b"not a sqlite database" + bytes(128))
        self.manifest["database"]["sha256"] = self.hash(self.db)
        self.save_manifest()
        before_db = self.hash(self.db)
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.hash(self.db), before_db)
        self.assertEqual(self.hash(self.epub), original_epub)
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse((self.root / ("anka.db" + suffix)).exists())

    def test_untracked_sqlite_sidecars_fail(self):
        for suffix in ("-wal", "-shm", "-journal"):
            with self.subTest(suffix=suffix):
                sidecar = self.root / ("anka.db" + suffix)
                sidecar.write_bytes(b"untracked-sqlite-state")
                self.assertNotEqual(self.verify().returncode, 0)
                self.assertEqual(sidecar.read_bytes(), b"untracked-sqlite-state")
                sidecar.unlink()

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

    def test_duplicate_manifest_json_keys_fail_without_modifying_data(self):
        original_db = self.hash(self.db)
        original_epub = self.hash(self.epub)
        valid = json.dumps(self.manifest)
        # A repeated key is ambiguous: different parsers may trust different values.
        malformed = valid[:-1] + ', "epubs": []}'
        (self.root / "manifest.json").write_text(malformed, encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate manifest JSON key", result.stderr)
        self.assertEqual(self.hash(self.db), original_db)
        self.assertEqual(self.hash(self.epub), original_epub)

    def test_nonstandard_json_numbers_fail_without_modifying_assets(self):
        original_db = self.hash(self.db)
        original_epub = self.hash(self.epub)
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                manifest = json.dumps(self.manifest)
                manifest = manifest[:-1] + ', "untrusted": ' + value + '}'
                (self.root / "manifest.json").write_text(manifest, encoding="utf-8")
                result = self.verify()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Non-standard JSON numeric value", result.stderr)
                self.assertEqual(self.hash(self.db), original_db)
                self.assertEqual(self.hash(self.epub), original_epub)

    def test_invalid_manifest_metadata_fails_without_modifying_assets(self):
        original_db = self.hash(self.db)
        original_epub = self.hash(self.epub)
        mutations = [
            lambda m: m.update({"database": []}),
            lambda m: m.update({"epubs": {}}),
            lambda m: m["database"].update({"sha256": "not-a-digest"}),
            lambda m: m["epubs"][0].update({"sha256": 42}),
            lambda m: m["epubs"][0].update({"size": -1}),
            lambda m: m["epubs"][0].update({"size": True}),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                self.manifest = {
                    "database": {"name": "anka.db", "sha256": original_db},
                    "epubs": [{"path": "epubs/sample.epub", "size": self.epub.stat().st_size,
                               "sha256": original_epub}],
                }
                mutate(self.manifest)
                self.save_manifest()
                result = self.verify()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.hash(self.db), original_db)
                self.assertEqual(self.hash(self.epub), original_epub)

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

    def test_symlinked_epub_directory_fails(self):
        outside = Path(self.tmp.name) / "external"
        outside.mkdir()
        (outside / "sample.epub").write_bytes(b"epub-fixture")
        self.epub.unlink()
        self.epub.parent.rmdir()
        try:
            (self.root / "epubs").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Directory symlinks unavailable: " + str(exc))
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertEqual((outside / "sample.epub").read_bytes(), b"epub-fixture")

    def test_unlisted_symlink_directory_fails(self):
        outside = Path(self.tmp.name) / "external"
        outside.mkdir()
        try:
            (self.epub.parent / "redirect").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Directory symlinks unavailable: " + str(exc))
        self.assertNotEqual(self.verify().returncode, 0)

if __name__ == "__main__":
    unittest.main()
