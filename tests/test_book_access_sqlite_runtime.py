"""Exercise the real SetBookAccessAsync SQLite statement against moderation transitions.

No production database or EPUB assets are opened by this test.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs"


def access_sql():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"public async Task<bool> SetBookAccessAsync\(.*?cmd\.CommandText=\x22\x22\x22(.*?)\x22\x22\x22;",
        source,
        re.S,
    )
    if not match:
        raise AssertionError("SetBookAccessAsync SQL statement not found")
    return match.group(1)


class BookAccessModerationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE anka_book_access(book_id TEXT PRIMARY KEY, access_mode TEXT, updated_utc TEXT);
            INSERT INTO books(id) VALUES ('approved'),('pending'),('rejected'),('legacy');
            INSERT INTO anka_book_moderation(book_id,state)
              VALUES ('approved','approved'),('pending','pending'),('rejected','rejected');
        """)
        self.sql = access_sql()

    def tearDown(self):
        self.db.close()

    def set_mode(self, book_id, mode):
        return self.db.execute(self.sql, {"id": book_id, "mode": mode}).rowcount

    def mode(self, book_id):
        row = self.db.execute(
            "SELECT access_mode FROM anka_book_access WHERE book_id=?", (book_id,)
        ).fetchone()
        return row[0] if row else None

    def test_pending_and_rejected_cannot_be_inserted(self):
        for book_id in ("pending", "rejected"):
            self.assertEqual(0, self.set_mode(book_id, "manual"))
            self.assertIsNone(self.mode(book_id))

    def test_approved_and_legacy_can_be_inserted_and_updated(self):
        for book_id in ("approved", "legacy"):
            self.assertEqual(1, self.set_mode(book_id, "manual"))
            self.assertEqual(1, self.set_mode(book_id, "free"))
            self.assertEqual("free", self.mode(book_id))

    def test_revoked_approval_blocks_upsert(self):
        self.assertEqual(1, self.set_mode("approved", "manual"))
        self.db.execute(
            "UPDATE anka_book_moderation SET state='rejected' WHERE book_id='approved'"
        )
        self.assertEqual(0, self.set_mode("approved", "free"))
        self.assertEqual("manual", self.mode("approved"))

    def test_pending_review_blocks_existing_access_mode_changes(self):
        self.assertEqual(1, self.set_mode("approved", "manual"))
        self.db.execute(
            "UPDATE anka_book_moderation SET state='pending' WHERE book_id='approved'"
        )
        self.assertEqual(0, self.set_mode("approved", "free"))
        self.assertEqual("manual", self.mode("approved"))
        self.db.execute(
            "UPDATE anka_book_moderation SET state='approved' WHERE book_id='approved'"
        )
        self.assertEqual(1, self.set_mode("approved", "free"))
        self.assertEqual("free", self.mode("approved"))

    def test_missing_book_cannot_create_access(self):
        self.assertEqual(0, self.set_mode("missing", "manual"))
        self.assertIsNone(self.mode("missing"))


if __name__ == "__main__":
    unittest.main()
