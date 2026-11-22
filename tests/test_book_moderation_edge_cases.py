"""Additional isolated moderation regressions for role and rights edge cases.

Uses the production SQL through the existing SQLite test harness; no production
database or EPUB assets are opened.
"""
import unittest
from test_book_moderation_sqlite import BookModerationSqlTests


class BookModerationEdgeCases(BookModerationSqlTests):
    def test_reader_uploader_cannot_be_approved(self):
        self.db.execute("UPDATE anka_users SET role='Reader' WHERE id='uploader'")
        self.assertEqual(self.review(), 0)

    def test_whitespace_only_rights_cannot_be_approved(self):
        self.db.execute("UPDATE anka_book_moderation SET rights_statement=?", (" " * 20,))
        self.assertEqual(self.review(), 0)

    def test_rejected_book_cannot_be_approved_later(self):
        self.assertEqual(self.review("rejected"), 1)
        self.assertEqual(self.review("approved"), 0)
        self.assertEqual(self.db.execute(
            "SELECT new_state FROM anka_book_review_history").fetchall(), [("rejected",)])

    def test_reviewer_revoked_before_review_creates_no_history(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='admin'")
        self.assertEqual(self.review("rejected"), 0)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM anka_book_review_history").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
