"""SQLite runtime checks for fail-closed moderation in access-policy writes."""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")

def statement(method, next_method):
    body = SOURCE.split("public async Task<bool> " + method + "(", 1)[1].split("public async Task<bool> " + next_method + "(", 1)[0]
    return re.search(r'cmd.CommandText="""(.*?)""";', body, re.S).group(1)

SET_ACCESS = statement("SetBookAccessAsync", "GrantBookToEmailAsync")
GRANT = statement("GrantBookToEmailAsync", "CanReadAsync")

class NullModerationAccessTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
          CREATE TABLE books(id TEXT PRIMARY KEY);
          CREATE TABLE anka_book_moderation(book_id TEXT,state TEXT);
          CREATE TABLE anka_book_access(book_id TEXT PRIMARY KEY,access_mode TEXT,updated_utc TEXT);
          CREATE TABLE anka_users(id TEXT,email TEXT,role TEXT,disabled INTEGER);
          CREATE TABLE anka_manual_entitlements(user_id TEXT,book_id TEXT,granted_by TEXT,reason TEXT,granted_utc TEXT,PRIMARY KEY(user_id,book_id));
          INSERT INTO books VALUES('book');
          INSERT INTO anka_users VALUES('admin','admin@example.test','Admin',0),('reader','reader@example.test','Reader',0);
        """)

    def tearDown(self):
        self.db.close()

    def test_policy_write_rejects_null_pending_and_rejected(self):
        for state in (None, "pending", "rejected"):
            with self.subTest(state=state):
                self.db.execute("DELETE FROM anka_book_moderation")
                self.db.execute("DELETE FROM anka_book_access")
                self.db.execute("INSERT INTO anka_book_moderation VALUES('book',?)", (state,))
                self.assertEqual(self.db.execute(SET_ACCESS, {"id":"book","mode":"manual"}).rowcount, 0)
                self.assertIsNone(self.db.execute("SELECT access_mode FROM anka_book_access").fetchone())

    def test_policy_update_rejects_null_moderation(self):
        self.db.execute("INSERT INTO anka_book_access VALUES('book','manual','old')")
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book',NULL)")
        self.db.execute(SET_ACCESS, {"id":"book","mode":"free"})
        self.assertEqual(self.db.execute("SELECT access_mode FROM anka_book_access").fetchone()[0], "manual")

    def test_entitlement_grant_rejects_null_moderation(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book',NULL)")
        self.assertEqual(self.db.execute(GRANT, {"email":"reader@example.test","book":"book","admin":"admin","reason":"test"}).rowcount, 0)

    def test_approved_book_allows_authorized_writes(self):
        self.db.execute("INSERT INTO anka_book_moderation VALUES('book','approved')")
        self.assertEqual(self.db.execute(SET_ACCESS, {"id":"book","mode":"manual"}).rowcount, 1)
        self.assertEqual(self.db.execute(GRANT, {"email":"reader@example.test","book":"book","admin":"admin","reason":"test"}).rowcount, 1)

if __name__ == "__main__":
    unittest.main()
