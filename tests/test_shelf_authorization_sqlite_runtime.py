"""Regression tests for shelf authorization against production SQLite statements.

These tests run in-memory only and never access production App_Data or EPUB files.
"""
from pathlib import Path
import re
import sqlite3
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")


def statement(method, next_method):
    # Generic Task<T> signatures must not be mistaken for plain Task.
    start = SOURCE.index(method)
    end = SOURCE.find(next_method, start + len(method))
    section = SOURCE[start:end if end != -1 else None]
    match = re.search(r'cmd\.CommandText="""(.*?)""";', section, re.S)
    if not match:
        raise AssertionError("Cannot locate production SQL for " + method)
    return match.group(1)


SHELF_SQL = statement("ShelfAsync(", "AddToShelfAsync(")
ADD_SQL = statement("AddToShelfAsync(", "OtherEditionsAsync(")

class ShelfAuthorizationSqliteRuntime(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE anka_users(id TEXT PRIMARY KEY, role TEXT, disabled INTEGER);
            CREATE TABLE books(id TEXT PRIMARY KEY);
            CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY, state TEXT);
            CREATE TABLE anka_book_access(book_id TEXT PRIMARY KEY, access_mode TEXT);
            CREATE TABLE anka_manual_entitlements(book_id TEXT, user_id TEXT);
            CREATE TABLE anka_user_shelves(user_id TEXT, book_id TEXT, added_utc TEXT,
                                           UNIQUE(user_id, book_id));
            INSERT INTO anka_users VALUES ('reader','Reader',0),('other','Reader',0),
                                          ('admin','Admin',0),('disabled','Reader',1);
            INSERT INTO books VALUES ('legacy'),('free'),('manual'),('pending'),
                                     ('rejected'),('revoked'),('paid');
            INSERT INTO anka_book_moderation VALUES
                ('free','approved'),('manual','approved'),('pending','pending'),
                ('rejected','rejected'),('revoked','approved'),('paid','approved');
            INSERT INTO anka_book_access VALUES
                ('free','free'),('manual','manual'),('pending','free'),
                ('rejected','free'),('revoked','manual'),('paid','paid');
            INSERT INTO anka_manual_entitlements VALUES ('manual','reader');
        """)

    def tearDown(self):
        self.db.close()

    def add(self, user, book):
        self.db.execute(ADD_SQL, {"u": user, "b": book})

    def visible(self, user):
        return set(row[0] for row in self.db.execute(SHELF_SQL, {"user": user}))

    def test_add_rejects_pending_rejected_paid_and_disabled_accounts(self):
        for book in ("legacy", "free", "manual", "pending", "rejected", "revoked", "paid"):
            self.add("reader", book)
        self.add("disabled", "free")
        self.add("other", "manual")
        self.assertEqual(self.visible("reader"), {"legacy", "free", "manual"})
        self.assertEqual(self.visible("disabled"), set())
        self.assertEqual(self.visible("other"), set())

    def test_revocation_hides_existing_entry_without_deleting_it(self):
        self.add("reader", "manual")
        self.assertIn("manual", self.visible("reader"))
        self.db.execute("DELETE FROM anka_manual_entitlements WHERE book_id='manual'")
        self.assertNotIn("manual", self.visible("reader"))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM anka_user_shelves WHERE book_id='manual'"
        ).fetchone()[0], 1)
        self.db.execute("INSERT INTO anka_manual_entitlements VALUES ('manual','reader')")
        self.assertIn("manual", self.visible("reader"))
        self.db.execute("UPDATE anka_book_moderation SET state='rejected' WHERE book_id='manual'")
        self.assertNotIn("manual", self.visible("reader"))

    def test_user_isolation_and_injection(self):
        self.add("reader", "free")
        self.assertEqual(self.visible("other"), set())
        self.assertEqual(self.visible("reader' OR 1=1 --"), set())
        self.add("reader", "free' OR 1=1 --")
        self.assertEqual(self.visible("reader"), {"free"})

    def test_admin_does_not_override_publication_or_paid_gates(self):
        for book in ("pending", "rejected", "paid", "revoked"):
            self.add("admin", book)
        self.assertEqual(self.visible("admin"), {"revoked"})


if __name__ == "__main__":
    unittest.main()
