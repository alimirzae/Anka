"""SQLite runtime regression for development-only account lookup SQL.

This exercises the actual SELECT extracted from AnkaAccountService, not a
reimplemented query. HTTP/Production smoke tests are still required.
"""
from pathlib import Path
import re
import sqlite3
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
METHOD = SOURCE.split("FindLocalTestAccountAsync(", 1)[1].split("public async Task<IReadOnlyList<AnkaPublisherRequest>>", 1)[0]
MATCH = re.search(r'cmd\.CommandText="(SELECT id,display_name,role FROM anka_users.*?)";', METHOD, re.S)


class LocalTestLoginSqliteRuntime(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(MATCH, "Cannot locate the production lookup SQL")
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE anka_users (id TEXT PRIMARY KEY, display_name TEXT, role TEXT, email TEXT, disabled INTEGER)")
        self.db.executemany(
            "INSERT INTO anka_users VALUES (?,?,?,?,?)",
            [
                ("reader", "Reader", "Reader", "reader@example.test", 0),
                ("admin", "Admin", "Admin", "admin@example.test", 0),
                ("publisher", "Publisher", "Publisher", "publisher@example.test", 0),
                ("disabled", "Disabled", "Reader", "disabled@example.test", 1),
            ],
        )

    def tearDown(self):
        self.db.close()

    def lookup(self, email):
        return self.db.execute(MATCH.group(1), {"email": email}).fetchone()

    def test_only_active_reader_is_eligible(self):
        self.assertEqual(self.lookup("reader@example.test"), ("reader", "Reader", "Reader"))
        for email in ("admin@example.test", "publisher@example.test", "disabled@example.test", "missing@example.test"):
            with self.subTest(email=email):
                self.assertIsNone(self.lookup(email))

    def test_injection_does_not_bypass_role_or_disabled_guard(self):
        for email in ("' OR 1=1 --", "admin@example.test' OR 1=1 --", "reader@example.test\x00"):
            with self.subTest(email=email):
                self.assertIsNone(self.lookup(email))
        self.assertEqual(self.db.execute("SELECT count(*) FROM anka_users").fetchone()[0], 4)


if __name__ == "__main__":
    unittest.main()
