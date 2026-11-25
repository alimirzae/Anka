"""Isolated regression tests for book moderation authorization and audit SQL.

The production UPDATE statement is extracted from AnkaAccountService.cs.
No production SQLite database or EPUB is accessed.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
MATCH = re.search(r'cmd\.CommandText="(UPDATE anka_book_moderation SET state=.*?)";', SOURCE)
if MATCH is None:
    raise RuntimeError("Book moderation SQL not found")
REVIEW_SQL = MATCH.group(1)


class BookModerationSqlTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_users(id TEXT PRIMARY KEY, role TEXT, disabled INTEGER);
            CREATE TABLE anka_book_moderation(
                book_id TEXT PRIMARY KEY, uploader_id TEXT, rights_statement TEXT,
                state TEXT, reviewed_by TEXT, created_utc TEXT, reviewed_utc TEXT
            );
            CREATE TABLE anka_book_rights_evidence(
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
                uploader_id TEXT NOT NULL,
                pdf_bytes BLOB NOT NULL CHECK(length(pdf_bytes) BETWEEN 5 AND 5242880),
                created_utc TEXT NOT NULL
            );
            CREATE TABLE anka_book_review_history(
                id INTEGER PRIMARY KEY, book_id TEXT, previous_state TEXT,
                new_state TEXT, reviewer_id TEXT, rights_statement TEXT, reviewed_utc TEXT
            );
            CREATE TRIGGER anka_record_book_review
            AFTER UPDATE OF state ON anka_book_moderation
            WHEN OLD.state='pending' AND NEW.state IN ('approved','rejected')
              AND NEW.reviewed_by IS NOT NULL AND NEW.reviewed_utc IS NOT NULL
            BEGIN
              INSERT INTO anka_book_review_history(
                book_id,previous_state,new_state,reviewer_id,rights_statement,reviewed_utc)
              VALUES(NEW.book_id,OLD.state,NEW.state,NEW.reviewed_by,
                NEW.rights_statement,NEW.reviewed_utc);
            END;
            INSERT INTO books VALUES('book');
            INSERT INTO anka_book_rights_evidence VALUES(
                'evidence','book','uploader',X'255044462D','now'
            );
            INSERT INTO anka_users VALUES('uploader','Publisher',0);
            INSERT INTO anka_users VALUES('admin','Admin',0);
            INSERT INTO anka_book_moderation VALUES(
                'book','uploader','Licensed publication rights','pending',NULL,'now',NULL
            );
        """)

    def review(self, state="approved", reviewer="admin"):
        return self.db.execute(REVIEW_SQL, {
            "state": state, "reviewer": reviewer, "id": "book"
        }).rowcount

    def test_active_admin_approves_and_audits_once(self):
        self.assertEqual(self.review(), 1)
        self.assertEqual(self.review(), 0)
        self.assertEqual(self.db.execute(
            "SELECT new_state,reviewer_id FROM anka_book_review_history"
        ).fetchall(), [("approved", "admin")])

    def test_missing_evidence_blocks_approval_but_not_rejection(self):
        self.db.execute("DELETE FROM anka_book_rights_evidence")
        self.assertEqual(self.review(), 0)
        self.assertEqual(self.review("rejected"), 1)

    def test_other_uploaders_evidence_cannot_authorize_approval(self):
        self.db.execute("UPDATE anka_book_rights_evidence SET uploader_id='admin'")
        self.assertEqual(self.review(), 0)

    def test_active_admin_can_reject(self):
        self.assertEqual(self.review("rejected"), 1)

    def test_uploader_cannot_review_own_book(self):
        self.db.execute("UPDATE anka_users SET role='Admin' WHERE id='uploader'")
        self.assertEqual(self.review(reviewer="uploader"), 0)

    def test_disabled_admin_cannot_review(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='admin'")
        self.assertEqual(self.review(), 0)

    def test_revoked_admin_cannot_review(self):
        self.db.execute("UPDATE anka_users SET role='Reader' WHERE id='admin'")
        self.assertEqual(self.review(), 0)

    def test_unknown_admin_cannot_review(self):
        self.assertEqual(self.review(reviewer="missing"), 0)

    def test_missing_book_cannot_be_approved(self):
        self.db.execute("DELETE FROM books WHERE id='book'")
        self.assertEqual(self.review(), 0)

    def test_disabled_uploader_cannot_be_approved(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='uploader'")
        self.assertEqual(self.review(), 0)

    def test_insufficient_rights_cannot_be_approved(self):
        self.db.execute("UPDATE anka_book_moderation SET rights_statement='no' ")
        self.assertEqual(self.review(), 0)

    def test_invalid_transition_does_not_change_state(self):
        self.assertEqual(self.review("published"), 0)
        self.assertEqual(self.db.execute(
            "SELECT state FROM anka_book_moderation"
        ).fetchone()[0], "pending")

    def test_denied_review_creates_no_audit_entry(self):
        self.assertEqual(self.review(reviewer="uploader"), 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM anka_book_review_history"
        ).fetchone()[0], 0)

    def test_rejection_allowed_when_rights_are_insufficient(self):
        self.db.execute("UPDATE anka_book_moderation SET rights_statement='no'")
        self.assertEqual(self.review("rejected"), 1)
        self.assertEqual(self.db.execute(
            "SELECT new_state FROM anka_book_review_history"
        ).fetchall(), [("rejected",)])

    def test_rejection_allowed_when_uploader_disabled(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='uploader'")
        self.assertEqual(self.review("rejected"), 1)

    def test_rights_statement_minimum_length_is_enforced(self):
        self.db.execute("UPDATE anka_book_moderation SET rights_statement=?", ("x" * 11,))
        self.assertEqual(self.review(), 0)
        self.db.execute("UPDATE anka_book_moderation SET rights_statement=?", ("x" * 12,))
        self.assertEqual(self.review(), 1)

    def test_rights_statement_maximum_length_is_enforced(self):
        self.db.execute("UPDATE anka_book_moderation SET rights_statement=?", ("x" * 2001,))
        self.assertEqual(self.review(), 0)
        self.db.execute("UPDATE anka_book_moderation SET rights_statement=?", ("x" * 2000,))
        self.assertEqual(self.review(), 1)

    def test_review_history_preserves_rights_statement(self):
        self.assertEqual(self.review(), 1)
        self.assertEqual(self.db.execute(
            "SELECT rights_statement FROM anka_book_review_history"
        ).fetchone()[0], "Licensed publication rights")


if __name__ == "__main__":
    unittest.main()
