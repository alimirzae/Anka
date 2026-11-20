"""Regression checks for EPUB upload size guards.

These source-level tests complement (do not replace) authenticated upload
integration tests. They prevent a guard being accidentally commented out.
"""
from pathlib import Path
import re
import unittest

PROGRAM = Path(__file__).resolve().parents[1] / "Program.cs"


class EpubGuardRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PROGRAM.read_text(encoding="utf-8")

    def test_mimetype_guard_is_executable(self):
        lines = self.source.splitlines()
        condition = re.compile(r"^\s*if\s*\(\s*mime\.Length\s*>\s*128\s*\)")
        matching = [i for i, line in enumerate(lines) if condition.search(line)]
        self.assertEqual(len(matching), 1, "Expected one executable mimetype size guard")
        i = matching[0]
        self.assertNotIn("//", lines[i].split("if", 1)[0])
        following = "\n".join(lines[i + 1:i + 4])
        self.assertIn("throw new InvalidDataException", following)
        self.assertLess(self.source.index("mime.Length > 128"), self.source.index("mime.Open()"))

    def test_xml_metadata_bounds_precede_parsing(self):
        for entry, limit, parse_call in (
            ("container", "1024 * 1024", "XDocument.Load(stream)"),
            ("opf", "4 * 1024 * 1024", "XDocument.Load(stream)"),
        ):
            guard = f"{entry}.Length > {limit}"
            self.assertIn(guard, self.source)
            start = self.source.index(guard)
            parse = self.source.index(parse_call, start)
            self.assertIn("throw new InvalidDataException", self.source[start:parse])

    def test_download_filename_is_bound_to_book_guid(self):
        # A compromised SQLite filename must never become an arbitrary disk path.
        route = self.source.index('app.MapGet("/api/books/{id:guid}/file"')
        end = self.source.index('app.MapPost("/api/books"', route)
        handler = self.source[route:end]
        guard = 'string.Equals(name, id.ToString("N") + ".epub", StringComparison.OrdinalIgnoreCase)'
        self.assertIn(guard, handler)
        self.assertLess(handler.index("CanReadAsync("), handler.index(guard))
        self.assertLess(handler.index(guard), handler.index("Path.Combine(storage, name)"))
        self.assertIn("return Results.NotFound();", handler[handler.index(guard):handler.index("Path.Combine(storage, name)")])

    def test_epub_download_disables_caching_before_authorization(self):
        # Entitlements can be revoked; private EPUB bytes must not remain
        # reusable in intermediary or browser HTTP caches.
        route = self.source.index('app.MapGet("/api/books/{id:guid}/file"')
        end = self.source.index('app.MapPost("/api/books"', route)
        handler = self.source[route:end]
        cache = 'context.Response.Headers["Cache-Control"] = "private, no-store";'
        pragma = 'context.Response.Headers["Pragma"] = "no-cache";'
        self.assertIn(cache, handler)
        self.assertIn(pragma, handler)
        self.assertLess(handler.index(cache), handler.index("CanReadAsync("))
        self.assertLess(handler.index(pragma), handler.index("CanReadAsync("))
        self.assertLess(handler.index("CanReadAsync("), handler.index("Results.File("))

    def test_ci_discovers_security_regressions(self):
        workflow = (PROGRAM.parent / ".github/workflows/anka-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("test_*.py", workflow)
        self.assertIn("tests/**", workflow)


if __name__ == "__main__":
    unittest.main()
