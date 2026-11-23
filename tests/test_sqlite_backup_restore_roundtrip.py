"""Isolated SQLite backup/restore regression: never opens production App_Data.

Run with: python -m unittest tests/test_sqlite_backup_restore_roundtrip.py
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path


class SQLiteBackupRestoreRoundtripTests(unittest.TestCase):
    def test_backup_preserves_committed_wal_data_and_foreign_keys(self):
        with tempfile.TemporaryDirectory(prefix="anka-backup-fixture-") as tmp:
            root = Path(tmp)
            source = root / "source.sqlite"
            snapshot = root / "snapshot.sqlite"
            restored = root / "restored.sqlite"
            with sqlite3.connect(source) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")
                db.execute("CREATE TABLE editions (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id), language TEXT NOT NULL)")
                db.execute("INSERT INTO books VALUES (1, 'Fixture only')")
                db.execute("INSERT INTO editions VALUES (2, 1, 'az-Arab')")
                db.commit()
                with sqlite3.connect(snapshot) as backup:
                    db.backup(backup)
            with sqlite3.connect(snapshot) as backup, sqlite3.connect(restored) as target:
                backup.backup(target)
            with sqlite3.connect(restored) as check:
                check.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(check.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(check.execute("SELECT title FROM books WHERE id=1").fetchone()[0], "Fixture only")
                self.assertEqual(check.execute("SELECT language FROM editions WHERE id=2").fetchone()[0], "az-Arab")

    def test_backup_does_not_modify_source_or_epub_fixture(self):
        with tempfile.TemporaryDirectory(prefix="anka-backup-fixture-") as tmp:
            root = Path(tmp)
            source = root / "source.sqlite"
            snapshot = root / "snapshot.sqlite"
            epub = root / "real-book-fixture.epub"
            epub.write_bytes(b"fixture EPUB bytes; never production data")
            original_epub = epub.read_bytes()
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE marker (value TEXT)")
                db.execute("INSERT INTO marker VALUES ('keep')")
                db.commit()
                with sqlite3.connect(snapshot) as backup:
                    db.backup(backup)
                self.assertEqual(db.execute("SELECT value FROM marker").fetchone()[0], "keep")
            self.assertEqual(epub.read_bytes(), original_epub)
            with sqlite3.connect(snapshot) as check:
                self.assertEqual(check.execute("SELECT value FROM marker").fetchone()[0], "keep")


if __name__ == "__main__":
    unittest.main()
