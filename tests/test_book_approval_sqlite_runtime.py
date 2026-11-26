"""Exercise production book-review SQL against isolated SQLite.

This guards the final database mutation even if endpoint authorization regresses.
It does not replace HTTP authorization or production smoke tests.
"""
from pathlib import Path
import re
import sqlite3
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
METHOD = SOURCE.split("public async Task<bool> ReviewBookAsync(", 1)[1].split("public async Task<bool> HasActiveAdminAsync(", 1)[0]
MATCH = re.search(r'cmd\.CommandText="(UPDATE anka_book_moderation SET .*?)";', METHOD, re.S)


class BookApprovalSqliteRuntime(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(MATCH, "Production book review SQL was not found")
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE anka_users(id TEXT PRIMARY KEY, role TEXT, disabled INTEGER);
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_book_moderation(
                book_id TEXT PRIMARY KEY, uploader_id TEXT, rights_statement TEXT,
                state TEXT, reviewed_by TEXT, reviewed_utc TEXT
            );
            CREATE TABLE anka_book_rights_evidence(
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
                uploader_id TEXT NOT NULL,
                pdf_bytes BLOB NOT NULL CHECK(length(pdf_bytes) BETWEEN 5 AND 5242880),
                created_utc TEXT NOT NULL
            );
            INSERT INTO anka_users VALUES
              ('admin','Admin',0),('inactive_admin','Admin',1),
              ('reader','Reader',0),('publisher','Publisher',0),
              ('inactive_publisher','Publisher',1);
            INSERT INTO books VALUES ('valid'),('short'),('inactive'),('missing');
            INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state)
              VALUES ('valid','publisher','Rights granted for this book','pending'),
                     ('short','publisher','none','pending'),
                     ('inactive','inactive_publisher','Rights granted for this book','pending'),
                     ('missing','publisher','Rights granted for this book','pending');
            INSERT INTO anka_book_rights_evidence VALUES
                ('e1','valid','publisher',X'255044462D','now'),
                ('e2','short','publisher',X'255044462D','now'),
                ('e3','inactive','inactive_publisher',X'255044462D','now'),
                ('e4','missing','publisher',X'255044462D','now');
            DELETE FROM books WHERE id='missing';
        """)

    def tearDown(self):
        self.db.close()

    def review(self, book, reviewer, state):
        return self.db.execute(MATCH.group(1), {"id": book, "reviewer": reviewer, "state": state}).rowcount

    def test_only_active_admin_can_approve(self):
        for reviewer in ("reader", "publisher", "inactive_admin", "nonexistent"):
            with self.subTest(reviewer=reviewer):
                self.assertEqual(self.review("valid", reviewer, "approved"), 0)
        self.assertEqual(self.review("valid", "admin", "approved"), 1)
        self.assertEqual(self.review("valid", "admin", "approved"), 0)
        self.assertEqual(self.db.execute("SELECT state,reviewed_by FROM anka_book_moderation WHERE book_id='valid'").fetchone(), ("approved", "admin"))

    def test_invalid_rights_or_uploader_cannot_be_approved(self):
        for book in ("short", "inactive", "missing"):
            with self.subTest(book=book):
                self.assertEqual(self.review(book, "admin", "approved"), 0)
                self.assertEqual(self.db.execute("SELECT state FROM anka_book_moderation WHERE book_id=?", (book,)).fetchone()[0], "pending")

    def test_admin_cannot_review_own_submission(self):
        self.db.execute("UPDATE anka_book_moderation SET uploader_id='admin' WHERE book_id='valid'")
        self.db.execute("UPDATE anka_book_rights_evidence SET uploader_id='admin' WHERE book_id='valid'")
        for state in ("approved", "rejected"):
            self.assertEqual(self.review("valid", "admin", state), 0)
        self.assertEqual(self.db.execute("SELECT state,reviewed_by FROM anka_book_moderation WHERE book_id='valid'").fetchone(), ("pending", None))
        self.db.execute("INSERT INTO anka_users VALUES ('second_admin','Admin',0)")
        self.assertEqual(self.review("valid", "second_admin", "approved"), 1)

    def test_revoked_publisher_cannot_be_approved(self):
        self.db.execute("UPDATE anka_users SET role='Reader' WHERE id='publisher'")
        self.assertEqual(self.review("valid", "admin", "approved"), 0)
        self.assertEqual(self.review("valid", "admin", "rejected"), 1)

    def test_missing_evidence_blocks_approval(self):
        self.db.execute("DELETE FROM anka_book_rights_evidence WHERE book_id='valid'")
        self.assertEqual(self.review("valid", "admin", "approved"), 0)
        self.assertEqual(self.review("valid", "admin", "rejected"), 1)

    def test_evidence_from_other_uploader_blocks_approval(self):
        self.db.execute("UPDATE anka_book_rights_evidence SET uploader_id='reader' WHERE book_id='valid'")
        self.assertEqual(self.review("valid", "admin", "approved"), 0)

    def test_rejection_requires_admin_and_existing_book(self):
        self.assertEqual(self.review("short", "reader", "rejected"), 0)
        self.assertEqual(self.review("missing", "admin", "rejected"), 0)
        self.assertEqual(self.review("short", "admin", "rejected"), 1)
        self.assertEqual(self.review("short", "admin", "approved"), 0)

    def test_sql_injection_and_invalid_state_do_not_mutate(self):
        for book in ("valid' OR 1=1 --", "valid\x00", "unknown"):
            self.assertEqual(self.review(book, "admin", "approved"), 0)
        self.assertEqual(self.review("valid", "admin", "published"), 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM anka_book_moderation WHERE state='pending'").fetchone()[0], 4)


if __name__ == "__main__":
    unittest.main()
