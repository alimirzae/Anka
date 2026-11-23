"""Isolated SQLite backup/restore regression: never opens production App_Data.

Run with: python -m unittest tests/test_sqlite_backup_restore_roundtrip.py
"""
import sqlite3
from contextlib import closing
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
            with closing(sqlite3.connect(source)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")
                db.execute("CREATE TABLE editions (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id), language TEXT NOT NULL)")
                db.execute("INSERT INTO books VALUES (1, 'Fixture only')")
                db.execute("INSERT INTO editions VALUES (2, 1, 'az-Arab')")
                db.commit()
                with closing(sqlite3.connect(snapshot)) as backup:
                    db.backup(backup)
            with closing(sqlite3.connect(snapshot) as backup, sqlite3.connect(restored)) as target:
                backup.backup(target)
            with closing(sqlite3.connect(restored)) as check:
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
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE marker (value TEXT)")
                db.execute("INSERT INTO marker VALUES ('keep')")
                db.commit()
                with closing(sqlite3.connect(snapshot)) as backup:
                    db.backup(backup)
                self.assertEqual(db.execute("SELECT value FROM marker").fetchone()[0], "keep")
            self.assertEqual(epub.read_bytes(), original_epub)
            with closing(sqlite3.connect(snapshot)) as check:
                self.assertEqual(check.execute("SELECT value FROM marker").fetchone()[0], "keep")


    def test_online_backup_is_consistent_while_wal_writer_remains_open(self):
        """An online snapshot must include committed rows but exclude uncommitted changes."""
        with tempfile.TemporaryDirectory(prefix="anka-online-backup-fixture-") as tmp:
            root = Path(tmp)
            source = root / "source.sqlite"
            snapshot = root / "snapshot.sqlite"
            with closing(sqlite3.connect(source, timeout=5)) as writer:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("CREATE TABLE editions (id INTEGER PRIMARY KEY, title TEXT NOT NULL)")
                writer.execute("INSERT INTO editions VALUES (1, 'committed edition')")
                writer.commit()
                # A second connection owns an uncommitted WAL transaction.
                with closing(sqlite3.connect(source, timeout=5)) as pending:
                    pending.execute("BEGIN IMMEDIATE")
                    pending.execute("INSERT INTO editions VALUES (2, 'uncommitted edition')")
                    with closing(sqlite3.connect(source, timeout=5)) as reader:
                        with closing(sqlite3.connect(snapshot)) as target:
                            reader.backup(target)
                    with closing(sqlite3.connect(snapshot)) as check:
                        self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                        self.assertEqual(check.execute("SELECT id FROM editions ORDER BY id").fetchall(), [(1,)])
                    pending.rollback()
                self.assertEqual(writer.execute("SELECT id FROM editions").fetchall(), [(1,)])

if __name__ == "__main__":
    unittest.main()
