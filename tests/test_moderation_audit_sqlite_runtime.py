"""SQLite regression: failed moderation must not stamp reviewer metadata."""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
BODY = SOURCE.split("public async Task<bool> ReviewBookAsync(", 1)[1].split("public async Task<bool> HasActiveAdminAsync(", 1)[0]
SQL = re.search(r'cmd\.CommandText="(UPDATE anka_book_moderation .*?)";', BODY, re.S).group(1)

class ModerationAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
          CREATE TABLE anka_users(id TEXT PRIMARY KEY,role TEXT,disabled INTEGER);
          CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY,uploader_id TEXT,
            rights_statement TEXT,state TEXT,reviewed_by TEXT,reviewed_utc TEXT);
          INSERT INTO anka_users VALUES('admin','Admin',0),('publisher','Publisher',0),
            ('reader','Reader',0);
          INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state)
            VALUES('book','publisher','I hold the publishing rights','pending');
        """)

    def tearDown(self):
        self.db.close()

    def attempt(self, reviewer, state):
        result = self.db.execute(SQL, {"id":"book","reviewer":reviewer,"state":state})
        record = self.db.execute(
            "SELECT state,reviewed_by,reviewed_utc FROM anka_book_moderation WHERE book_id='book'"
        ).fetchone()
        return result.rowcount, record

    def test_unauthorized_review_leaves_audit_fields_empty(self):
        for reviewer in ("reader", "missing", None):
            with self.subTest(reviewer=reviewer):
                changed, record = self.attempt(reviewer, "approved")
                self.assertEqual(changed, 0)
                self.assertEqual(record, ("pending", None, None))

    def test_successful_review_stamps_reviewer_and_timestamp(self):
        changed, record = self.attempt("admin", "approved")
        self.assertEqual(changed, 1)
        self.assertEqual(record[0:2], ("approved", "admin"))
        self.assertRegex(record[2], r"^\d{4}-\d{2}-\d{2}T")

    def test_repeated_review_does_not_overwrite_audit(self):
        self.attempt("admin", "approved")
        original = self.db.execute(
            "SELECT state,reviewed_by,reviewed_utc FROM anka_book_moderation WHERE book_id='book'"
        ).fetchone()
        changed, record = self.attempt("admin", "rejected")
        self.assertEqual(changed, 0)
        self.assertEqual(record, original)

if __name__ == "__main__":
    unittest.main()
