"""Exercise the actual moderation SQL against an isolated SQLite database."""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")


class ReviewHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        schema = re.search(r'cmd\.CommandText\s*=\s*"""(.*?)"""', SOURCE, re.S).group(1)
        self.db.executescript(schema)
        self.db.execute("CREATE TABLE books(id TEXT PRIMARY KEY)")
        for uid, role, disabled in (("admin", "Admin", 0), ("publisher", "Publisher", 0),
                                    ("reader", "Reader", 0), ("disabled", "Admin", 1)):
            self.db.execute("INSERT INTO anka_users VALUES(?,?,?,?,?,?,?)",
                            (uid, uid+"@example.test", uid, "unused", role, disabled, "now"))
        self.db.execute("INSERT INTO books VALUES('book')")
        self.db.execute("INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,created_utc) VALUES(?,?,?,?)",
                        ("book", "publisher", "Valid rights declaration", "now"))
        self.db.commit()
        self.sql = re.search(r'cmd\.CommandText="(UPDATE anka_book_moderation SET state=.*?)";', SOURCE).group(1)

    def review(self, reviewer="admin", state="approved"):
        return self.db.execute(self.sql, dict(id="book", reviewer=reviewer, state=state)).rowcount

    def history(self):
        return self.db.execute("SELECT book_id,previous_state,new_state,reviewer_id,rights_statement FROM anka_book_review_history").fetchall()

    def test_approval_records_once(self):
        self.assertEqual(self.review(), 1)
        self.assertEqual(self.review(state="rejected"), 0)
        self.assertEqual(self.history(), [("book","pending","approved","admin","Valid rights declaration")])

    def test_rejection_records_decision(self):
        self.assertEqual(self.review(state="rejected"), 1)
        self.assertEqual(self.history()[0][2], "rejected")

    def test_unauthorized_has_no_history(self):
        for reviewer in ("reader", "publisher", "disabled"):
            self.assertEqual(self.review(reviewer), 0)
        self.assertEqual(self.history(), [])

    def test_history_failure_rolls_back_decision(self):
        self.db.execute("CREATE TRIGGER fail_history BEFORE INSERT ON anka_book_review_history BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.review()
        self.assertEqual(self.db.execute("SELECT state FROM anka_book_moderation").fetchone()[0], "pending")
        self.assertEqual(self.history(), [])


if __name__ == "__main__":
    unittest.main()
