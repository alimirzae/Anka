"""Regression tests for publisher approval transaction predicates using isolated SQLite.

The SQL is extracted from production source to catch authorization regressions.
No production database or uploaded EPUB is opened.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")


class PublisherApprovalSqlTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        schema = re.search(r'cmd\.CommandText\s*=\s*"""(.*?)"""', SOURCE, re.S)
        self.assertIsNotNone(schema)
        self.db.executescript(schema.group(1))
        self.db.execute("INSERT INTO anka_users VALUES(?,?,?,?,?,?,?)",
                        ("applicant", "applicant@example.test", "Applicant", "hash", "Reader", 0, "now"))
        self.db.execute("INSERT INTO anka_publisher_requests(user_id,statement,state,requested_utc) VALUES(?,?,?,?)",
                        ("applicant", "I own the rights", "pending", "now"))
        self.db.execute("INSERT INTO anka_users VALUES(?,?,?,?,?,?,?)",
                        ("admin", "admin@example.test", "Admin", "hash", "Admin", 0, "now"))
        self.db.commit()
        match = re.search(r'cmd\.CommandText="(UPDATE anka_publisher_requests SET state=.*?)";', SOURCE)
        self.assertIsNotNone(match)
        self.review_sql = match.group(1)
        match = re.search(r'cmd\.CommandText="(UPDATE anka_users SET role=\x27Publisher\x27.*?)";', SOURCE)
        self.assertIsNotNone(match)
        self.promote_sql = match.group(1)

    def test_pending_active_reader_can_be_approved(self):
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "admin"}).rowcount, 1)
        self.assertEqual(self.db.execute(self.promote_sql, {"id": "applicant"}).rowcount, 1)
        self.assertEqual(self.db.execute("SELECT role FROM anka_users WHERE id='applicant'").fetchone()[0], "Publisher")

    def test_disabled_applicant_cannot_be_approved(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='applicant'")
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "admin"}).rowcount, 0)
        self.assertEqual(self.db.execute("SELECT state FROM anka_publisher_requests").fetchone()[0], "pending")

    def test_non_reader_cannot_be_approved(self):
        self.db.execute("UPDATE anka_users SET role='Publisher' WHERE id='applicant'")
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "admin"}).rowcount, 0)

    def test_review_cannot_be_repeated(self):
        self.assertEqual(self.db.execute(self.review_sql, {"state": "rejected", "id": "applicant", "reviewer": "admin"}).rowcount, 1)
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "admin"}).rowcount, 0)


    def test_disabled_admin_cannot_review(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='admin'")
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "admin"}).rowcount, 0)

    def test_revoked_admin_cannot_review(self):
        self.db.execute("UPDATE anka_users SET role='Reader' WHERE id='admin'")
        self.assertEqual(self.db.execute(self.review_sql, {"state": "rejected", "id": "applicant", "reviewer": "admin"}).rowcount, 0)

    def test_unknown_reviewer_cannot_review(self):
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "missing"}).rowcount, 0)

    def test_self_review_is_rejected(self):
        self.db.execute("UPDATE anka_users SET role='Admin' WHERE id='applicant'")
        self.assertEqual(self.db.execute(self.review_sql, {"state": "approved", "id": "applicant", "reviewer": "applicant"}).rowcount, 0)

    def test_rejected_application_does_not_promote(self):
        self.assertEqual(self.db.execute(self.review_sql, {"state": "rejected", "id": "applicant", "reviewer": "admin"}).rowcount, 1)
        self.assertEqual(self.db.execute("SELECT role FROM anka_users WHERE id='applicant'").fetchone()[0], "Reader")


if __name__ == "__main__":
    unittest.main()
