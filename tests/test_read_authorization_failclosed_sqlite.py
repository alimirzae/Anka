"""Fail-closed SQLite regression for public and entitled book reads."""
import pathlib
import re
import sqlite3
import unittest

source = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
body = source.split("public async Task<bool> CanReadAsync(", 1)[1].split("public async Task<IReadOnlyList<string>> ShelfAsync(", 1)[0]
SQL = re.search(r'cmd\.CommandText="""(.*?)"""', body, re.S).group(1)


class ReadAuthorizationSqliteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_book_moderation(book_id TEXT, state TEXT);
            CREATE TABLE anka_book_access(book_id TEXT, access_mode TEXT);
            CREATE TABLE anka_manual_entitlements(book_id TEXT, user_id TEXT);
            CREATE TABLE anka_users(id TEXT PRIMARY KEY, role TEXT, disabled INTEGER);
            INSERT INTO books VALUES('book');
            INSERT INTO anka_users VALUES('reader','Reader',0),('admin','Admin',0),
                                         ('disabled','Reader',1);
        """)

    def tearDown(self):
        self.db.close()

    def can_read(self, user=""):
        return self.db.execute(SQL, {"book": "book", "user": user}).fetchone()[0] == 1

    def test_pending_rejected_and_null_moderation_are_hidden(self):
        for state in ("pending", "rejected", None):
            with self.subTest(state=state):
                self.db.execute("DELETE FROM anka_book_moderation")
                self.db.execute("INSERT INTO anka_book_moderation VALUES('book',?)", (state,))
                self.assertFalse(self.can_read())
                self.assertFalse(self.can_read("admin"))

    def test_approved_free_book_is_public(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_book_access VALUES('book','free')")
        self.assertTrue(self.can_read())

    def test_manual_requires_active_entitlement_or_admin(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_book_access VALUES('book','manual')")
        self.assertFalse(self.can_read())
        self.assertFalse(self.can_read("reader"))
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        self.assertTrue(self.can_read("reader"))
        self.assertTrue(self.can_read("admin"))
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='reader'")
        self.assertFalse(self.can_read("reader"))
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='admin'")
        self.assertFalse(self.can_read("admin"))

    def test_invalid_policy_is_denied_even_with_entitlement_or_admin(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        for mode in (None, "", "premium", "MANUAL", "manual "):
            with self.subTest(mode=mode):
                self.db.execute("DELETE FROM anka_book_access")
                self.db.execute("INSERT INTO anka_book_access VALUES('book',?)", (mode,))
                self.assertFalse(self.can_read())
                self.assertFalse(self.can_read("reader"))
                self.assertFalse(self.can_read("admin"))


    def test_mixed_valid_and_invalid_access_rows_fail_closed(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        for invalid in (None, "", "premium"):
            with self.subTest(invalid=invalid):
                self.db.execute("DELETE FROM anka_book_access")
                self.db.execute("INSERT INTO anka_book_access VALUES('book','free')")
                self.db.execute("INSERT INTO anka_book_access VALUES('book',?)", (invalid,))
                for user in ("", "reader", "admin"):
                    self.assertFalse(self.can_read(user))


if __name__ == "__main__":
    unittest.main()
