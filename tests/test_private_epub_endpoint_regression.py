"""Guard private EPUB endpoints against future authorization/cache regressions.

These are source-level checks, not substitutes for HTTP integration tests.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


def endpoint(start_marker, end_marker):
    start = SOURCE.index(start_marker)
    return SOURCE[start:SOURCE.index(end_marker, start)]


class PrivateEpubEndpointRegressionTests(unittest.TestCase):
    def test_file_download_checks_entitlement_before_storage_access(self):
        handler = endpoint('app.MapGet("/api/books/{id:guid}/file"', 'app.MapPost("/api/books"')
        authorization = handler.index("accounts.CanReadAsync(")
        storage_read = handler.index("SELECT filename FROM books")
        self.assertLess(authorization, storage_read)
        self.assertIn('Results.StatusCode(403)', handler)
        self.assertIn('Cache-Control', handler)
        self.assertIn('private, no-store', handler)
        self.assertIn('Pragma', handler)

    def test_reading_diagnostics_checks_entitlement_before_parsing(self):
        handler = endpoint('app.MapGet("/api/books/{id:guid}/reading-status"', 'app.MapGet("/api/books",')
        self.assertLess(handler.index("accounts.CanReadAsync("), handler.index("reader.OpenAsync(id)"))
        self.assertIn('Results.StatusCode(403)', handler)
        self.assertIn('private, no-store', handler)
        self.assertIn('Pragma', handler)


if __name__ == "__main__":
    unittest.main()
