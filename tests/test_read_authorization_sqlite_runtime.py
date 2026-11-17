"""Execute the production CanReadAsync authorization query against isolated SQLite.

No production database or EPUB content is opened.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs"


def read_sql():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"public async Task<bool> CanReadAsync\(.*?cmd\.CommandText=\x22\x22\x22(.*?)\x22\x22\x22;",
        source, re.S,
    )
    if not match:
        raise AssertionError("CanReadAsync SQL not found")
    return match.group(1)


class ReadAuthorizationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY, state TEXT);
            CREATE TABLE anka_book_access(book_id TEXT PRIMARY KEY, access_mode TEXT);
            CREATE TABLE anka_users(id TEXT PRIMARY KEY, role TEXT, disabled INTEGER);
            CREATE TABLE anka_manual_entitlements(user_id TEXT, book_id TEXT);
            INSERT INTO books(id) VALUES ('free'),('manual'),('pending'),('rejected'),('legacy');
            INSERT INTO anka_book_access(book_id,access_mode) VALUES
                ('manual','manual'),('pending','manual'),('rejected','free');
            INSERT INTO anka_book_moderation(book_id,state) VALUES
                ('manual','approved'),('pending','pending'),('rejected','rejected');
            INSERT INTO anka_users(id,role,disabled) VALUES
                ('reader','Reader',0),('other','Reader',0),
                ('disabled','Reader',1),('admin','Admin',0),
                ('disabled_admin','Admin',1);
            INSERT INTO anka_manual_entitlements(user_id,book_id) VALUES
                ('reader','manual'),('disabled','manual');
        """)
        self.sql = read_sql()

    def tearDown(self):
        self.db.close()

    def can_read(self, user, book):
        return bool(self.db.execute(
            self.sql, {"user": user or "", "book": book}
        ).fetchone()[0])

    def test_public_free_and_legacy_remain_readable(self):
        for book in ("free", "legacy"):
            with self.subTest(book=book):
                self.assertTrue(self.can_read(None, book))

    def test_manual_book_requires_entitlement_or_active_admin(self):
        for user, allowed in (
            (None, False), ("other", False), ("reader", True),
            ("disabled", False), ("admin", True),
            ("disabled_admin", False), ("unknown", False),
        ):
            with self.subTest(user=user):
                self.assertEqual(allowed, self.can_read(user, "manual"))

    def test_pending_and_rejected_are_hidden_even_from_admin(self):
        for book in ("pending", "rejected"):
            for user in (None, "reader", "admin"):
                with self.subTest(book=book, user=user):
                    self.assertFalse(self.can_read(user, book))

    def test_revoking_approval_immediately_blocks_existing_entitlement(self):
        self.assertTrue(self.can_read("reader", "manual"))
        self.db.execute(
            "UPDATE anka_book_moderation SET state='pending' WHERE book_id='manual'"
        )
        self.assertFalse(self.can_read("reader", "manual"))
        self.assertFalse(self.can_read("admin", "manual"))

    def test_disabling_entitled_user_revokes_read_access(self):
        self.assertTrue(self.can_read("reader", "manual"))
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='reader'")
        self.assertFalse(self.can_read("reader", "manual"))

    def test_entitlement_is_scoped_to_exact_user_and_book(self):
        self.assertTrue(self.can_read("reader", "manual"))
        self.assertFalse(self.can_read("other", "manual"))
        self.db.execute(
            "INSERT INTO anka_manual_entitlements(user_id,book_id) VALUES (?,?)",
            ("other", "nonexistent"),
        )
        self.assertFalse(self.can_read("other", "manual"))
        self.assertFalse(self.can_read("other", "nonexistent"))

    def test_rejection_overrides_existing_entitlement_and_admin_role(self):
        self.assertTrue(self.can_read("reader", "manual"))
        self.db.execute(
            "UPDATE anka_book_moderation SET state='rejected' WHERE book_id='manual'"
        )
        for user in ("reader", "admin", None):
            with self.subTest(user=user):
                self.assertFalse(self.can_read(user, "manual"))

    def test_null_moderation_state_denies_every_reader(self):
        self.assertTrue(self.can_read("reader", "manual"))
        self.db.execute(
            "UPDATE anka_book_moderation SET state=NULL WHERE book_id='manual'"
        )
        for user in (None, "reader", "admin"):
            with self.subTest(user=user):
                self.assertFalse(self.can_read(user, "manual"))

    def test_null_moderation_state_denies_free_book(self):
        self.db.execute(
            "UPDATE anka_book_moderation SET state=NULL WHERE book_id='rejected'"
        )
        for user in (None, "reader", "admin"):
            with self.subTest(user=user):
                self.assertFalse(self.can_read(user, "rejected"))

    def test_unknown_moderation_states_fail_closed(self):
        """Only explicitly approved moderation states may expose a book."""
        for state in ("APPROVED", "approved ", "", "draft", "withdrawn"):
            with self.subTest(state=state):
                self.db.execute(
                    "UPDATE anka_book_moderation SET state=? WHERE book_id='manual'",
                    (state,),
                )
                for user in (None, "reader", "admin"):
                    self.assertFalse(self.can_read(user, "manual"))

    def test_invalid_access_modes_fail_closed(self):
        """Unknown, empty and null access modes cannot become public books."""
        for mode in ("MANUAL", "manual ", "", "premium", None):
            with self.subTest(mode=mode):
                self.db.execute(
                    "UPDATE anka_book_access SET access_mode=? WHERE book_id='manual'",
                    (mode,),
                )
                for user in (None, "reader", "other"):
                    # An existing manual entitlement must not bypass invalid policy.
                    self.assertFalse(self.can_read(user, "manual"))

    def test_explicit_free_access_remains_public(self):
        self.db.execute(
            "UPDATE anka_book_access SET access_mode='free' WHERE book_id='manual'"
        )
        self.assertTrue(self.can_read(None, "manual"))

    def test_missing_book_is_never_readable(self):
        self.assertFalse(self.can_read("admin", "nonexistent"))


if __name__ == "__main__":
    unittest.main()
