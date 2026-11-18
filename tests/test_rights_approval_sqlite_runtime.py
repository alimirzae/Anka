"""Runtime SQLite regression for the book moderation approval gate."""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
BODY = SOURCE.split("public async Task<bool> ReviewBookAsync(", 1)[1].split("public async Task<bool> HasActiveAdminAsync(", 1)[0]
SQL = re.search(r'cmd\.CommandText="(UPDATE anka_book_moderation .*?)";', BODY, re.S).group(1)

class RightsApprovalSqliteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
          CREATE TABLE books(id TEXT PRIMARY KEY);
          INSERT INTO books(id) VALUES ('book');
          CREATE TABLE anka_users(id TEXT PRIMARY KEY,role TEXT,disabled INTEGER);
          CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY,uploader_id TEXT,
            rights_statement TEXT,state TEXT,reviewed_by TEXT,reviewed_utc TEXT);
          INSERT INTO anka_users VALUES('admin','Admin',0),('publisher','Publisher',0),
            ('reader','Reader',0),('disabled','Publisher',1);
        """)

    def tearDown(self):
        self.db.close()

    def review(self, uploader, rights, state="approved", reviewer="admin"):
        self.db.execute("DELETE FROM anka_book_moderation")
        self.db.execute("INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state) VALUES('book',?,?,'pending')", (uploader, rights))
        result = self.db.execute(SQL, {"id":"book","reviewer":reviewer,"state":state})
        return result.rowcount, self.db.execute("SELECT state FROM anka_book_moderation WHERE book_id='book'").fetchone()[0]

    def test_valid_publisher_can_be_approved(self):
        self.assertEqual(self.review("publisher","I own publication rights"), (1,"approved"))

    def test_invalid_rights_cannot_be_approved(self):
        for rights in ("", "short", "   ", "x"*2001):
            with self.subTest(rights=rights[:12]):
                self.assertEqual(self.review("publisher",rights), (0,"pending"))

    def test_unapproved_or_disabled_uploader_cannot_be_approved(self):
        for uploader in ("reader","disabled","missing"):
            with self.subTest(uploader=uploader):
                self.assertEqual(self.review(uploader,"I own publication rights"), (0,"pending"))

    def test_inactive_reviewer_cannot_approve(self):
        self.assertEqual(self.review("publisher","I own publication rights",reviewer="reader"), (0,"pending"))

    def test_disabled_admin_cannot_review(self):
        self.db.execute("INSERT INTO anka_users VALUES('disabled_admin','Admin',1)")
        for state in ("approved", "rejected"):
            with self.subTest(state=state):
                self.assertEqual(self.review("publisher", "I own publication rights", state=state, reviewer="disabled_admin"), (0, "pending"))

    def test_non_pending_submission_cannot_be_reviewed_again(self):
        for initial in ("approved", "rejected", "withdrawn", ""):
            with self.subTest(initial=initial):
                self.db.execute("DELETE FROM anka_book_moderation")
                self.db.execute("INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state) VALUES('book','publisher','I own publication rights',?)", (initial,))
                result = self.db.execute(SQL, {"id": "book", "reviewer": "admin", "state": "approved"})
                self.assertEqual(result.rowcount, 0)
                self.assertEqual(self.db.execute("SELECT state FROM anka_book_moderation WHERE book_id='book'").fetchone()[0], initial)

    def test_null_rights_or_uploader_fail_closed(self):
        for uploader, rights in (("publisher", None), (None, "I own publication rights")):
            with self.subTest(uploader=uploader, rights=rights):
                self.assertEqual(self.review(uploader, rights), (0, "pending"))

    def test_publisher_revocation_before_review_blocks_approval(self):
        self.db.execute("UPDATE anka_users SET role='Reader' WHERE id='publisher'")
        self.assertEqual(self.review("publisher", "I own publication rights"), (0, "pending"))

    def test_deleted_book_cannot_be_approved_or_rejected(self):
        # A stale moderation row must not be actionable after its book is deleted.
        self.db.execute("DELETE FROM books WHERE id='book'")
        for decision in ("approved", "rejected"):
            with self.subTest(decision=decision):
                self.assertEqual(
                    self.review("publisher", "I own publication rights", state=decision),
                    (0, "pending"),
                )

    def test_denied_review_preserves_existing_audit_fields(self):
        # A rejected authorization attempt must not forge an approval audit trail.
        for reviewer in ("reader", "disabled", "missing"):
            with self.subTest(reviewer=reviewer):
                self.db.execute("DELETE FROM anka_book_moderation")
                self.db.execute(
                    "INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state,reviewed_by,reviewed_utc) "
                    "VALUES('book','publisher','I own publication rights','pending',NULL,NULL)"
                )
                result = self.db.execute(SQL, {"id": "book", "reviewer": reviewer, "state": "approved"})
                self.assertEqual(result.rowcount, 0)
                audit = self.db.execute(
                    "SELECT state,reviewed_by,reviewed_utc FROM anka_book_moderation WHERE book_id='book'"
                ).fetchone()
                self.assertEqual(audit, ("pending", None, None))

    def test_moderation_sql_rejects_unrecognized_decisions_without_audit_changes(self):
        # Defense in depth: even a future caller bypassing the bool API cannot
        # turn an arbitrary state into a published/approved submission.
        for decision in ("published", "pending", "withdrawn", "", "APPROVED", None):
            with self.subTest(decision=decision):
                self.db.execute("DELETE FROM anka_book_moderation")
                self.db.execute(
                    "INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state,reviewed_by,reviewed_utc) "
                    "VALUES('book','publisher','I own publication rights','pending',NULL,NULL)"
                )
                result = self.db.execute(SQL, {
                    "id": "book", "reviewer": "admin", "state": decision
                })
                self.assertEqual(result.rowcount, 0)
                self.assertEqual(
                    self.db.execute(
                        "SELECT state,reviewed_by,reviewed_utc FROM anka_book_moderation WHERE book_id='book'"
                    ).fetchone(),
                    ("pending", None, None),
                )

    def test_admin_can_reject_invalid_submission(self):
        self.assertEqual(self.review("reader","short",state="rejected"), (1,"rejected"))

if __name__ == "__main__":
    unittest.main()
