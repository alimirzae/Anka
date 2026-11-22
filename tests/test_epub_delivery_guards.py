"""Source-level fail-closed checks for private EPUB delivery.

These tests inspect the real endpoint implementation without touching App_Data.
They complement, but do not replace, authenticated HTTP integration tests.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class EpubDeliveryGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start = SOURCE.index('app.MapGet("/api/books/{id:guid}/file"')
        end = SOURCE.index('app.MapPost("/api/books"', start)
        cls.handler = SOURCE[start:end]

    def test_authorization_precedes_database_and_file_access(self):
        h = self.handler
        self.assertIn("accounts.CanReadAsync(", h)
        self.assertIn("return Results.StatusCode(403)", h)
        self.assertLess(h.index("accounts.CanReadAsync("), h.index("new SqliteConnection("))
        self.assertLess(h.index("accounts.CanReadAsync("), h.index("Results.File("))

    def test_download_is_not_cacheable_or_sniffable(self):
        h = self.handler
        self.assertIn('Headers["Cache-Control"] = "private, no-store"', h)
        self.assertIn('Headers["Pragma"] = "no-cache"', h)
        self.assertIn('Headers["X-Content-Type-Options"] = "nosniff"', h)

    def test_filename_must_match_generated_guid_and_reparse_points_rejected(self):
        h = self.handler
        self.assertIn('id.ToString("N") + ".epub"', h)
        self.assertIn("StringComparison.OrdinalIgnoreCase", h)
        self.assertIn("FileAttributes.ReparsePoint", h)
        self.assertLess(h.index("FileAttributes.ReparsePoint"), h.index("Results.File("))

    def test_sql_query_is_parameterized(self):
        h = self.handler
        self.assertIn("WHERE id=@id", h)
        self.assertIn('AddWithValue("@id", id.ToString())', h)


if __name__ == "__main__":
    unittest.main()
