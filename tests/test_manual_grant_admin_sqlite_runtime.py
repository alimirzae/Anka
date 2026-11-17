"""Runtime regression tests for administrator-granted reading access.

Extracts the SQL from the production service and runs it on an isolated,
in-memory SQLite database. Never touches deployed data or EPUB files.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs"


def grant_sql():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"public async Task<bool> GrantBookToEmailAsync\(.*?cmd\.CommandText=\x22\x22\x22(.*?)\x22\x22\x22;",
        source,
        re.S,
    )
    if not match:
        raise AssertionError("GrantBookToEmailAsync SQL not found")
    return match.group(1)


class ManualGrantAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE anka_users(
                id TEXT PRIMARY KEY, email TEXT UNIQUE, role TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE anka_manual_entitlements(
                user_id TEXT NOT NULL, book_id TEXT NOT NULL,
                granted_by TEXT NOT NULL, reason TEXT, granted_utc TEXT,
                PRIMARY KEY(user_id, book_id));
            INSERT INTO anka_users(id,email,role,disabled) VALUES
                ('admin','admin@example.test','Admin',0),
                ('disabled_admin','disabled-admin@example.test','Admin',1),
                ('reader','reader@example.test','Reader',0),
                ('disabled_reader','disabled-reader@example.test','Reader',1),
                ('publisher','publisher@example.test','Publisher',0);
            INSERT INTO books(id) VALUES ('approved'),('pending'),('rejected'),('legacy');
            INSERT INTO anka_book_moderation(book_id,state) VALUES
                ('approved','approved'),('pending','pending'),('rejected','rejected');
        """)
        self.sql = grant_sql()

    def tearDown(self):
        self.db.close()

    def grant(self, admin="admin", book="approved", email="reader@example.test"):
        return self.db.execute(
            self.sql, {"admin": admin, "book": book,
                       "email": email, "reason": "manual test grant"}
        ).rowcount

    def count(self):
        return self.db.execute(
            "SELECT COUNT(*) FROM anka_manual_entitlements"
        ).fetchone()[0]

    def test_active_admin_can_grant_approved_or_legacy_book(self):
        self.assertEqual(1, self.grant())
        self.assertEqual(1, self.grant(book="legacy"))
        self.assertEqual(2, self.count())

    def test_non_admin_disabled_admin_and_missing_actor_denied(self):
        for actor in ("reader", "publisher", "disabled_admin", "missing"):
            with self.subTest(actor=actor):
                self.assertEqual(0, self.grant(admin=actor))
                self.assertEqual(0, self.count())

    def test_pending_rejected_and_missing_books_denied(self):
        for book in ("pending", "rejected", "missing"):
            with self.subTest(book=book):
                self.assertEqual(0, self.grant(book=book))
                self.assertEqual(0, self.count())

    def test_disabled_and_unknown_recipient_denied(self):
        for email in ("disabled-reader@example.test", "missing@example.test"):
            with self.subTest(email=email):
                self.assertEqual(0, self.grant(email=email))
                self.assertEqual(0, self.count())

    def test_duplicate_grant_is_idempotent(self):
        self.assertEqual(1, self.grant())
        self.assertEqual(0, self.grant())
        self.assertEqual(1, self.count())

    def test_revoked_approval_blocks_new_grants(self):
        self.assertEqual(1, self.grant())
        self.db.execute(
            "UPDATE anka_book_moderation SET state='pending' WHERE book_id='approved'"
        )
        self.assertEqual(
            0, self.grant(email="publisher@example.test")
        )
        self.assertEqual(1, self.count())


if __name__ == "__main__":
    unittest.main()
