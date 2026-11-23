"""Verify failed book audit writes cannot leave an approved book behind.

Uses the real schema on an in-memory database only; never opens App_Data.
"""
import sqlite3
import unittest

from test_book_review_audit import schema


class BookAuditAtomicityTests(unittest.TestCase):
    def test_audit_insert_failure_rolls_back_moderation_transition(self):
        db = sqlite3.connect(":memory:")
        try:
            db.executescript(schema())
            db.execute(
                "INSERT INTO anka_book_moderation "
                "(book_id,uploader_id,rights_statement,state,created_utc) "
                "VALUES(?,?,?,?,?)",
                ("atomic-book", "publisher", "original rights", "pending", "2026-01-01"),
            )
            db.execute("""
                CREATE TRIGGER reject_audit_insert
                BEFORE INSERT ON anka_book_review_history
                BEGIN
                    SELECT RAISE(ABORT, 'simulated audit write failure');
                END
            """)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "UPDATE anka_book_moderation "
                    "SET state='approved',reviewed_by='admin',reviewed_utc='2026-01-02' "
                    "WHERE book_id='atomic-book'"
                )
            self.assertEqual(
                db.execute(
                    "SELECT state FROM anka_book_moderation WHERE book_id='atomic-book'"
                ).fetchone()[0],
                "pending",
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM anka_book_review_history").fetchone()[0],
                0,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
