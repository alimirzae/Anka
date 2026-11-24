"""Regression tests for the actual ReviewBookAsync SQL; no production data."""
import re
import sqlite3
import unittest

from test_book_review_audit import SOURCE, schema


class RightsEvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript(schema())
        # Minimal projection of the separate catalog table used by this query.
        self.db.execute("CREATE TABLE books(id TEXT PRIMARY KEY)")
        self.db.execute("INSERT INTO books VALUES ('book')")
        for uid, role in (("owner", "Publisher"), ("other", "Publisher"),
                          ("admin", "Admin"), ("reader", "Reader")):
            self.db.execute(
                "INSERT INTO anka_users(id,email,display_name,password_hash,role,created_utc)"
                " VALUES(?,?,?,?,?,?)", (uid, uid+"@example.invalid", uid, "unused", role, "2026-01-01"))
        self.db.execute(
            "INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state,created_utc)"
            " VALUES('book','owner','original licensed statement','pending','2026-01-01')")
        source = SOURCE.read_text(encoding="utf-8").split("public async Task<bool> ReviewBookAsync(", 1)[1]
        self.sql = re.search(r'cmd\.CommandText\s*=\s*"([^"]+)"\s*;', source).group(1)

    def evidence(self, owner="owner", book="book"):
        self.db.execute("INSERT INTO anka_book_rights_evidence VALUES(?,?,?,?,?)",
                        ("evidence", book, owner, b"%PDF-test", "2026-01-01"))

    def review(self, state="approved", reviewer="admin", expected=0):
        self.assertEqual(self.db.execute(self.sql, dict(id="book", state=state, reviewer=reviewer)).rowcount, expected)
        self.assertEqual(self.db.execute("SELECT state FROM anka_book_moderation").fetchone()[0],
                         state if expected else "pending")
        self.assertEqual(self.db.execute("SELECT count(*) FROM anka_book_review_history").fetchone()[0], expected)

    def test_missing_evidence(self):
        self.review()

    def test_other_publisher_evidence(self):
        self.evidence(owner="other")
        self.review()

    def test_other_book_evidence(self):
        self.evidence(book="different")
        self.review()

    def test_owner_evidence(self):
        self.evidence()
        self.review(expected=1)

    def test_rejection_without_evidence(self):
        self.review(state="rejected", expected=1)

    def test_disabled_admin(self):
        self.evidence()
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='admin'")
        self.review()

    def test_disabled_publisher(self):
        self.evidence()
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='owner'")
        self.review()

    def test_non_admin(self):
        self.evidence()
        self.review(reviewer="reader")


if __name__ == "__main__":
    unittest.main()
