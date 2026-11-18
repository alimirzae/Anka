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


    def test_conflicting_free_and_manual_rows_are_denied_for_every_role(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_book_access VALUES('book','free')")
        self.db.execute("INSERT INTO anka_book_access VALUES('book','manual')")
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        for user in ("", "reader", "admin"):
            with self.subTest(user=user):
                self.assertFalse(self.can_read(user))


    def test_mixed_approved_and_unapproved_moderation_rows_fail_closed(self):
        self.db.execute("INSERT INTO anka_book_access VALUES('book','free')")
        for state in ("pending", "rejected", "withdrawn", None):
            with self.subTest(state=state):
                self.db.execute("DELETE FROM anka_book_moderation")
                self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
                self.db.execute("INSERT INTO anka_book_moderation VALUES('book',?)", (state,))
                for user in ("", "reader", "admin"):
                    self.assertFalse(self.can_read(user))

    def test_moderated_book_without_access_policy_is_not_public(self):
        # A missing policy must not silently grant free access to new submissions.
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        for user in ("", "reader", "admin"):
            with self.subTest(user=user):
                self.assertFalse(self.can_read(user))

    def test_legacy_unmoderated_book_remains_readable_without_policy(self):
        # Existing pre-moderation EPUBs must not disappear during additive migration.
        for user in ("", "reader"):
            self.assertTrue(self.can_read(user))

    def test_entitlements_are_scoped_to_the_exact_book_and_user(self):
        # An entitlement for a different book or account cannot authorize this title.
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_book_access VALUES('book','manual')")
        self.db.execute("INSERT INTO books VALUES('other')")
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('other','reader')")
        self.assertFalse(self.can_read("reader"))
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','someone-else')")
        self.assertFalse(self.can_read("reader"))
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        self.assertTrue(self.can_read("reader"))

    def test_unknown_book_is_never_readable_even_for_admin(self):
        self.db.execute("DELETE FROM books WHERE id='book'")
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.db.execute("INSERT INTO anka_book_access VALUES('book','free')")
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES('book','reader')")
        for user in ("", "reader", "admin"):
            with self.subTest(user=user):
                self.assertFalse(self.can_read(user))

if __name__ == "__main__":
    unittest.main()
