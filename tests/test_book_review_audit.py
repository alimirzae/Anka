"""Book moderation audit regression tests; uses only in-memory SQLite."""
import pathlib
import re
import sqlite3
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs"


def schema():
    match = re.search(r'cmd\.CommandText\s*=\s*"""(.*?)"""\s*;', SOURCE.read_text(encoding="utf-8"), re.S)
    if not match:
        raise AssertionError("Cannot locate SQLite schema")
    return match.group(1)


class BookReviewAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(schema())
        self.db.execute(
            "INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state,created_utc) "
            "VALUES('book1','publisher1','original licensed statement','pending','2026-01-01')"
        )

    def tearDown(self):
        self.db.close()

    def test_approval_creates_immutable_decision(self):
        self.db.execute(
            "UPDATE anka_book_moderation SET state='approved',reviewed_by='admin1',"
            "reviewed_utc='2026-01-02' WHERE book_id='book1'"
        )
        expected = ('pending', 'approved', 'admin1', 'original licensed statement')
        query = ("SELECT previous_state,new_state,reviewer_id,rights_statement "
                 "FROM anka_book_review_history WHERE book_id='book1'")
        self.assertEqual(self.db.execute(query).fetchone(), expected)
        for sql in (
            "UPDATE anka_book_review_history SET new_state='rejected'",
            "DELETE FROM anka_book_review_history",
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.assertEqual(self.db.execute(query).fetchone(), expected)

    def test_rereview_records_every_decision_without_noop_duplicates(self):
        self.db.execute(
            "UPDATE anka_book_moderation SET state='approved',reviewed_by='admin1',"
            "reviewed_utc='2026-01-02' WHERE book_id='book1'"
        )
        self.db.execute(
            "UPDATE anka_book_moderation SET state='rejected',reviewed_by='admin2',"
            "reviewed_utc='2026-01-03' WHERE book_id='book1'"
        )
        self.db.execute(
            "UPDATE anka_book_moderation SET state='rejected' WHERE book_id='book1'"
        )
        rows = self.db.execute(
            "SELECT previous_state,new_state,reviewer_id "
            "FROM anka_book_review_history WHERE book_id='book1' ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, [
            ('pending', 'approved', 'admin1'),
            ('approved', 'rejected', 'admin2'),
        ])

    def test_state_change_without_reviewer_cannot_bypass_audit(self):
        for update in (
            "state='approved'",
            "state='rejected',reviewed_by='admin1'",
            "state='approved',reviewed_utc='2026-01-02'",
            "state='approved',reviewed_by='  ',reviewed_utc='2026-01-02'",
            "state='unreviewed',reviewed_by='admin1',reviewed_utc='2026-01-02'",
        ):
            with self.subTest(update=update), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute("UPDATE anka_book_moderation SET " + update + " WHERE book_id='book1'")
        self.assertEqual(self.db.execute(
            "SELECT state FROM anka_book_moderation WHERE book_id='book1'"
        ).fetchone()[0], "pending")
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM anka_book_review_history"
        ).fetchone()[0], 0)

    def test_rollback_does_not_leave_review_record(self):
        self.db.execute("SAVEPOINT review")
        self.db.execute(
            "UPDATE anka_book_moderation SET state='rejected',reviewed_by='admin1',"
            "reviewed_utc='2026-01-02' WHERE book_id='book1'"
        )
        self.db.execute("ROLLBACK TO review")
        self.db.execute("RELEASE review")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM anka_book_review_history").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT state FROM anka_book_moderation").fetchone()[0], "pending")


if __name__ == "__main__":
    unittest.main()
