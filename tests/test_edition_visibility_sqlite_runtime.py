"""Runtime regression tests for Book/Edition publication filtering.

Executes the SQL embedded in OtherEditionsAsync against an isolated in-memory
SQLite database; never touches production SQLite or EPUB assets.
"""
import pathlib
import re
import sqlite3
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs"


def edition_sql():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"public async Task<IReadOnlyList<AnkaEditionInfo>> OtherEditionsAsync\(.*?cmd\.CommandText=\x22\x22\x22(.*?)\x22\x22\x22;",
        source, re.S,
    )
    if not match:
        raise AssertionError("OtherEditionsAsync SQL not found")
    return match.group(1)


class EditionVisibilityRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE books(id TEXT PRIMARY KEY, title TEXT NOT NULL);
            CREATE TABLE anka_editions(
                book_id TEXT PRIMARY KEY, work_id TEXT NOT NULL,
                language TEXT NOT NULL, content_status TEXT NOT NULL,
                translator TEXT NOT NULL DEFAULT '',
                publisher_name TEXT NOT NULL DEFAULT '');
            CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY, state TEXT);
            INSERT INTO books VALUES
                ('az','Az'),('tr','Tr'),('pending','Pending'),
                ('rejected','Rejected'),('unrelated','Unrelated');
            INSERT INTO anka_editions(book_id,work_id,language,content_status)
                VALUES ('az','work','az-Arab','complete'),
                       ('tr','work','tr','complete'),
                       ('pending','work','en','complete'),
                       ('rejected','work','fa','complete'),
                       ('unrelated','another','en','complete');
            INSERT INTO anka_book_moderation VALUES
                ('az','approved'),('tr','approved'),
                ('pending','pending'),('rejected','rejected'),
                ('unrelated','approved');
        """)
        self.sql = edition_sql()

    def tearDown(self):
        self.db.close()

    def visible(self, book_id):
        return [row[0] for row in self.db.execute(self.sql, {"id": book_id})]

    def test_approved_source_only_lists_approved_editions_of_same_work(self):
        self.assertEqual(["az", "tr"], self.visible("az"))

    def test_pending_or_rejected_source_cannot_reveal_related_editions(self):
        self.assertEqual([], self.visible("pending"))
        self.assertEqual([], self.visible("rejected"))

    def test_revocation_immediately_removes_edition_from_selector(self):
        self.db.execute(
            "UPDATE anka_book_moderation SET state='pending' WHERE book_id='tr'"
        )
        self.assertEqual(["az"], self.visible("az"))
        self.assertEqual([], self.visible("tr"))

    def test_missing_source_cannot_enumerate_editions(self):
        self.assertEqual([], self.visible("missing"))

    def test_unrelated_work_is_not_mixed_into_selector(self):
        self.assertEqual(["unrelated"], self.visible("unrelated"))


if __name__ == "__main__":
    unittest.main()
