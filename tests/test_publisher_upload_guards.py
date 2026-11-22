"""Regression checks for hostile publisher EPUB uploads.

These source guards are not substitutes for HTTP integration/fuzz tests.
They never open production SQLite or EPUB assets.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")
START = SOURCE.index('app.MapPost("/api/books"')
END = SOURCE.index('app.Map', START + 12) if 'app.Map' in SOURCE[START + 12:] else len(SOURCE)
UPLOAD = SOURCE[START:END]


class PublisherUploadGuards(unittest.TestCase):
    def test_authorization_and_rights_before_multipart_parse(self):
        self.assertIn("SameOrigin(request)", UPLOAD)
        self.assertIn('IsCurrentRoleAsync(uploader,"Publisher")', UPLOAD)
        self.assertIn('IsCurrentRoleAsync(uploader,"Admin")', UPLOAD)
        self.assertIn('rightsDeclaration.Length<12', UPLOAD)
        self.assertLess(UPLOAD.index("rightsDeclaration.Length<12"), UPLOAD.index("ReadFormAsync()"))

    def test_epub_zip_bomb_and_traversal_guards(self):
        for marker in ("archive.Entries.Count > 15000", "200L * 1024 * 1024",
                       "entryName.StartsWith('/')", "entryName.Contains('\\\\')",
                       'part is "." or ".."', "!entryNames.Add(entryName)",
                       "entry.CompressedLength", "InvalidDataException"):
            self.assertIn(marker, UPLOAD)

    def test_xml_external_entities_are_disabled(self):
        self.assertGreaterEqual(UPLOAD.count("DtdProcessing.Prohibit"), 2)
        self.assertGreaterEqual(UPLOAD.count("XmlResolver = null"), 2)
        self.assertIn("MaxCharactersInDocument", UPLOAD)

    def test_pending_moderation_and_edition_share_transaction(self):
        self.assertIn("BeginTransactionAsync()", UPLOAD)
        self.assertIn("INSERT INTO anka_book_moderation", UPLOAD)
        self.assertIn("'pending'", UPLOAD)
        self.assertIn("INSERT INTO anka_works", UPLOAD)
        self.assertIn("INSERT INTO anka_editions", UPLOAD)
        self.assertIn("transaction", UPLOAD)


if __name__ == "__main__":
    unittest.main()
