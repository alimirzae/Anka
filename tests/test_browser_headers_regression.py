"""Source-level regression for ANKA's browser security response headers.

This complements HTTP/IIS smoke tests; it does not assert deployed behavior.
"""
from pathlib import Path
import unittest

PROGRAM = Path(__file__).resolve().parents[1] / "Program.cs"


class BrowserHeadersRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PROGRAM.read_text(encoding="utf-8")

    def test_frame_protection_applies_before_routes(self):
        source = self.source
        header = 'context.Response.Headers.TryAdd("X-Frame-Options", "DENY")'
        self.assertIn(header, source)
        self.assertLess(source.index(header), source.index("app.UseStaticFiles()"))
        self.assertLess(source.index(header), source.index("app.UseAuthentication()"))
        self.assertIn("context.Response.OnStarting(", source[:source.index(header)])

    def test_private_account_and_moderation_api_are_not_cached(self):
        source = self.source
        start = source.index('context.Request.Path.StartsWithSegments("/api/account")')
        end = source.index('context.Response.Headers["Pragma"] = "no-cache";', start)
        segment = source[start:end]
        for route in ("/api/account", "/api/admin", "/api/publisher", "/api/me"):
            self.assertIn(f'StartsWithSegments("{route}")', segment)
        self.assertIn('context.Response.Headers["Cache-Control"] = "no-store";', segment)

    def test_content_sniffing_protection(self):
        source = self.source
        self.assertIn('context.Response.Headers.TryAdd("X-Content-Type-Options", "nosniff")', source)


if __name__ == "__main__":
    unittest.main()
