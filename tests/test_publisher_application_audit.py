"""Regression tests for publisher application audit triggers using the real schema.

Run: python -m unittest discover -s tests -p 'test_publisher_application_audit.py'
No production database or EPUB is opened.
"""
import pathlib
import re
import sqlite3
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AnkaAccountService.cs"


def schema():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r'cmd\.CommandText\s*=\s*"""(.*?)"""\s*;', source, re.S)
    if not match:
        raise AssertionError("Cannot locate EnsureCreatedAsync SQL schema")
    return match.group(1)


class PublisherApplicationAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(schema())
        self.db.execute(
            "INSERT INTO anka_users(id,email,display_name,password_hash,created_utc) "
            "VALUES('u1','publisher@example.invalid','Publisher','test-only','2026-01-01')"
        )

    def tearDown(self):
        self.db.close()

    def history(self):
        return self.db.execute(
            "SELECT previous_state,previous_statement,new_state,new_statement "
            "FROM anka_publisher_application_history ORDER BY id"
        ).fetchall()

    def test_initial_application_and_resubmission_preserve_statements(self):
        self.db.execute(
            "INSERT INTO anka_publisher_requests(user_id,statement,requested_utc) "
            "VALUES('u1','first rights declaration','2026-01-01')"
        )
        self.db.execute(
            "UPDATE anka_publisher_requests SET state='rejected' WHERE user_id='u1'"
        )
        self.db.execute(
            "UPDATE anka_publisher_requests SET state='pending', "
            "statement='revised rights declaration' WHERE user_id='u1'"
        )
        self.assertEqual(self.history(), [
            ("none", "", "pending", "first rights declaration"),
            ("pending", "first rights declaration", "rejected", "first rights declaration"),
            ("rejected", "first rights declaration", "pending", "revised rights declaration"),
        ])

    def test_noop_update_does_not_duplicate_audit(self):
        self.db.execute(
            "INSERT INTO anka_publisher_requests(user_id,statement,requested_utc) "
            "VALUES('u1','rights','2026-01-01')"
        )
        self.db.execute(
            "UPDATE anka_publisher_requests SET statement=statement,state=state "
            "WHERE user_id='u1'"
        )
        self.assertEqual(len(self.history()), 1)

    def test_rolled_back_application_leaves_no_audit(self):
        self.db.execute("SAVEPOINT application")
        self.db.execute(
            "INSERT INTO anka_publisher_requests(user_id,statement,requested_utc) "
            "VALUES('u1','uncommitted','2026-01-01')"
        )
        self.db.execute("ROLLBACK TO application")
        self.db.execute("RELEASE application")
        self.assertEqual(self.history(), [])
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM anka_publisher_requests").fetchone()[0], 0
        )


    def test_application_audit_rejects_update_and_delete(self):
        self.db.execute(
            "INSERT INTO anka_publisher_requests(user_id,statement,requested_utc) "
            "VALUES('u1','original declaration','2026-01-01')"
        )
        original = self.history()
        for sql in (
            "UPDATE anka_publisher_application_history SET new_statement='tampered'",
            "DELETE FROM anka_publisher_application_history",
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.assertEqual(self.history(), original)

    def test_admin_decision_audit_rejects_update_and_delete(self):
        self.db.execute(
            "INSERT INTO anka_publisher_review_history"
            "(user_id,reviewer_id,previous_state,new_state,statement,reviewed_utc) "
            "VALUES('u1','u1','pending','rejected','test declaration','2026-01-01')"
        )
        for sql in (
            "UPDATE anka_publisher_review_history SET new_state='approved'",
            "DELETE FROM anka_publisher_review_history",
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.assertEqual(
            self.db.execute("SELECT new_state FROM anka_publisher_review_history").fetchone()[0],
            "rejected",
        )


if __name__ == "__main__":
    unittest.main()
