"""Runtime SQLite regression tests for admin-only book moderation.

The SQL is extracted from the production service. All fixtures are in-memory;
no deployed SQLite database or real EPUB file is accessed.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs"


def review_sql():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"public async Task<bool> ReviewBookAsync\(.*?cmd\.CommandText=\"([^\"]+)\";",
        source,
        re.S,
    )
    if not match:
        raise AssertionError("ReviewBookAsync SQL not found")
    return match.group(1)


class BookReviewAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE anka_users(id TEXT PRIMARY KEY, role TEXT NOT NULL,
                                    disabled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE anka_book_moderation(
                book_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                rights_statement TEXT, uploader_id TEXT,
                reviewed_by TEXT, reviewed_utc TEXT);
            INSERT INTO anka_users(id,role,disabled) VALUES
                ('admin','Admin',0),('disabled_admin','Admin',1),
                ('reader','Reader',0),('publisher','Publisher',0);
            INSERT INTO anka_book_moderation(book_id,state,rights_statement,uploader_id) VALUES
                ('pending','pending','Licensed by the copyright holder','publisher'),
                ('approved','approved','Licensed by the copyright holder','publisher'),
                ('rejected','rejected','Licensed by the copyright holder','publisher'),
                ('no_rights','pending',NULL,'publisher'),
                ('no_uploader','pending','Licensed by the copyright holder','missing');
        """)
        self.sql = review_sql()

    def tearDown(self):
        self.db.close()

    def review(self, book, reviewer, state="approved"):
        return self.db.execute(
            self.sql, {"id": book, "reviewer": reviewer, "state": state}
        ).rowcount

    def state(self, book):
        return self.db.execute(
            "SELECT state,reviewed_by FROM anka_book_moderation WHERE book_id=?",
            (book,),
        ).fetchone()

    def test_active_admin_can_approve_pending(self):
        self.assertEqual(1, self.review("pending", "admin"))
        self.assertEqual(("approved", "admin"), self.state("pending"))

    def test_active_admin_can_reject_pending(self):
        self.assertEqual(1, self.review("pending", "admin", "rejected"))
        self.assertEqual(("rejected", "admin"), self.state("pending"))

    def test_non_admin_disabled_admin_and_unknown_user_denied(self):
        for reviewer in ("reader", "publisher", "disabled_admin", "missing"):
            with self.subTest(reviewer=reviewer):
                self.assertEqual(0, self.review("pending", reviewer))
                self.assertEqual(("pending", None), self.state("pending"))

    def test_approval_requires_rights_and_active_uploader(self):
        for book in ('no_rights', 'no_uploader'):
            with self.subTest(book=book):
                self.assertEqual(0, self.review(book, 'admin'))
                self.assertEqual(('pending', None), self.state(book))

    def test_rejection_allowed_without_valid_rights(self):
        self.assertEqual(1, self.review('no_rights', 'admin', 'rejected'))
        self.assertEqual(('rejected', 'admin'), self.state('no_rights'))

    def test_approval_denied_after_uploader_role_revoked_or_disabled(self):
        for change in ("UPDATE anka_users SET role='Reader' WHERE id='publisher'",
                       "UPDATE anka_users SET disabled=1 WHERE id='publisher'"):
            with self.subTest(change=change):
                self.db.execute(change)
                self.assertEqual(0, self.review("pending", "admin"))
                self.assertEqual(("pending", None), self.state("pending"))
                self.db.execute("UPDATE anka_users SET role='Publisher',disabled=0 WHERE id='publisher'")

    def test_rights_statement_length_and_whitespace_boundaries(self):
        for statement, allowed in (("", False), ("   ", False),
                                   ("x" * 11, False), ("x" * 12, True),
                                   ("x" * 2000, True), ("x" * 2001, False)):
            with self.subTest(length=len(statement)):
                self.db.execute(
                    "UPDATE anka_book_moderation SET state='pending',reviewed_by=NULL,rights_statement=? WHERE book_id='pending'",
                    (statement,),
                )
                self.assertEqual(int(allowed), self.review("pending", "admin"))
                self.assertEqual("approved" if allowed else "pending", self.state("pending")[0])

    def test_already_reviewed_and_missing_books_denied(self):
        for book in ("approved", "rejected", "missing"):
            with self.subTest(book=book):
                self.assertEqual(0, self.review(book, "admin"))
        self.assertEqual(("approved", None), self.state("approved"))
        self.assertEqual(("rejected", None), self.state("rejected"))


if __name__ == "__main__":
    unittest.main()
