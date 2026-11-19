"""Additional publication-revocation regression tests using production edition SQL."""
from pathlib import Path
import re
import sqlite3
import unittest

source = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
section = source.split("public async Task<IReadOnlyList<AnkaEditionInfo>> OtherEditionsAsync(", 1)[1].split("public async Task<bool> LinkEditionAsync(", 1)[0]
match = re.search(r'cmd\.CommandText="""(.*?)""";', section, re.S)
if not match:
    raise AssertionError("OtherEditionsAsync SQL missing")
SQL = match.group(1)

class EditionRevocationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE books(id TEXT PRIMARY KEY,title TEXT);
            CREATE TABLE anka_editions(book_id TEXT PRIMARY KEY,work_id TEXT,
                language TEXT,content_status TEXT,translator TEXT,publisher_name TEXT);
            CREATE TABLE anka_book_moderation(book_id TEXT PRIMARY KEY,state TEXT);
            INSERT INTO books VALUES ('az','AZ'),('tr','TR'),('legacy','Legacy'),('other','Other');
            INSERT INTO anka_editions VALUES
                ('az','work','az-Arab','complete','',''),
                ('tr','work','tr','complete','',''),
                ('legacy','work','en','complete','',''),
                ('other','another','en','complete','','');
            INSERT INTO anka_book_moderation VALUES ('az','approved'),('tr','approved');
        """)

    def tearDown(self):
        self.db.close()

    def visible(self, book):
        return [row[0] for row in self.db.execute(SQL, {"id": book})]

    def test_revoked_edition_disappears_and_restores_only_on_approval(self):
        self.assertEqual(self.visible("az"), ["az", "tr", "legacy"])
        self.db.execute("UPDATE anka_book_moderation SET state='rejected' WHERE book_id='tr'")
        self.assertEqual(self.visible("az"), ["az", "legacy"])
        self.db.execute("UPDATE anka_book_moderation SET state='pending' WHERE book_id='tr'")
        self.assertEqual(self.visible("az"), ["az", "legacy"])
        self.db.execute("UPDATE anka_book_moderation SET state='approved' WHERE book_id='tr'")
        self.assertEqual(self.visible("az"), ["az", "tr", "legacy"])

    def test_revoked_source_cannot_list_approved_siblings(self):
        self.db.execute("UPDATE anka_book_moderation SET state='rejected' WHERE book_id='az'")
        self.assertEqual(self.visible("az"), [])
        self.assertEqual(self.visible("tr"), ["tr", "legacy"])

    def test_edition_lookup_is_parameterized(self):
        self.assertEqual(self.visible("az' OR 1=1 --"), [])
        self.assertEqual(self.visible("unknown"), [])

if __name__ == "__main__":
    unittest.main()
