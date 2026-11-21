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
            ("container", "1024 * 1024", "XDocument.Load(reader)"),
            ("opf", "4 * 1024 * 1024", "XDocument.Load(reader)"),
        ):
            guard = f"{entry}.Length > {limit}"
            self.assertIn(guard, self.source)
            start = self.source.index(guard)
            parse = self.source.index(parse_call, start)
            self.assertIn("throw new InvalidDataException", self.source[start:parse])

    def test_epub_metadata_xml_disallows_dtd_and_external_resolution(self):
        # Both untrusted metadata documents must use explicitly hardened XML readers.
        self.assertEqual(self.source.count("DtdProcessing = System.Xml.DtdProcessing.Prohibit"), 2)
        self.assertEqual(self.source.count("XmlResolver = null"), 2)
        self.assertEqual(self.source.count("XDocument.Load(reader)"), 2)
        self.assertIn("MaxCharactersInDocument = 1024 * 1024", self.source)
        self.assertIn("MaxCharactersInDocument = 4 * 1024 * 1024", self.source)

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

    def test_epub_download_disables_content_type_sniffing(self):
        # Uploaded EPUBs are untrusted; browsers must honor the declared MIME type.
        route = self.source.index('app.MapGet("/api/books/{id:guid}/file"')
        end = self.source.index('app.MapPost("/api/books"', route)
        handler = self.source[route:end]
        nosniff = 'context.Response.Headers["X-Content-Type-Options"] = "nosniff";'
        self.assertIn(nosniff, handler)
        self.assertLess(handler.index(nosniff), handler.index("CanReadAsync("))
        self.assertLess(handler.index("CanReadAsync("), handler.index("Results.File("))
        self.assertIn('"application/epub+zip"', handler)

    def test_epub_download_rejects_reparse_points(self):
        # A valid GUID filename must not allow symlinks to external EPUB data.
        route = self.source.index('app.MapGet("/api/books/{id:guid}/file"')
        end = self.source.index('app.MapPost("/api/books"', route)
        handler = self.source[route:end]
        self.assertIn("new FileInfo(path)", handler)
        self.assertIn("FileAttributes.ReparsePoint", handler)
        self.assertLess(handler.index("FileAttributes.ReparsePoint"), handler.index("Results.File("))
        self.assertIn("return Results.NotFound();", handler[handler.index("FileAttributes.ReparsePoint"):handler.index("Results.File(")])

    def test_fixed_test_pin_is_development_loopback_only(self):
        # The fixed PIN must never become a public-site authentication path.
        route = self.source.index('app.MapPost("/api/account/test-login"')
        start = self.source.rfind("if(app.Environment.IsDevelopment()", 0, route)
        self.assertGreaterEqual(start, 0, "Test-login route must be inside a Development guard")
        prefix = self.source[start:route]
        self.assertIn('ANKA_ENABLE_LOCAL_TEST_LOGIN', prefix)
        self.assertIn('"true"', prefix)
        end = self.source.index('}).RequireRateLimiting("account");', route)
        handler = self.source[route:end]
        self.assertIn("IPAddress.IsLoopback(context.Connection.RemoteIpAddress", handler)
        self.assertIn("IPAddress.IsLoopback(hostIp)", handler)
        self.assertIn('context.Request.Host.Host, "localhost"', handler)
        self.assertIn("SameOrigin(context.Request)", handler)
        self.assertIn('input.Pin!="1234"', handler)
        self.assertLess(handler.index("IPAddress.IsLoopback(context.Connection.RemoteIpAddress"),
                        handler.index("context.SignInAsync("))
        self.assertLess(handler.index('input.Pin!="1234"'), handler.index("context.SignInAsync("))

    def test_ci_discovers_security_regressions(self):
        workflow = (PROGRAM.parent / ".github/workflows/anka-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("test_*.py", workflow)
        self.assertIn("tests/**", workflow)


if __name__ == "__main__":
    unittest.main()
