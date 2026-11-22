"""Regression guards for revocation of authenticated sessions.

These are source-level checks only; deployed HTTP tests remain necessary.
No production SQLite database or EPUB files are opened.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class SessionRevocationGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start = SOURCE.index("options.Events.OnValidatePrincipal=")
        end = SOURCE.index("options.Events.OnRedirectToLogin=", start)
        cls.validation = SOURCE[start:end]

    def test_cookie_revalidates_current_account_role(self):
        h = self.validation
        self.assertIn("ClaimTypes.NameIdentifier", h)
        self.assertIn("ClaimTypes.Role", h)
        self.assertIn("accounts.IsCurrentRoleAsync(id,role)", h)

    def test_revoked_or_missing_account_rejects_and_signs_out(self):
        h = self.validation
        self.assertIn("string.IsNullOrWhiteSpace(id)", h)
        self.assertIn("string.IsNullOrWhiteSpace(role)", h)
        self.assertIn("!await accounts.IsCurrentRoleAsync(id,role)", h)
        self.assertIn("context.RejectPrincipal()", h)
        self.assertIn("context.HttpContext.SignOutAsync(", h)
        self.assertLess(h.index("context.RejectPrincipal()"), h.index("context.HttpContext.SignOutAsync("))

    def test_cookie_is_secure_httponly_and_strict_samesite(self):
        start = SOURCE.index(".AddCookie(options=>")
        end = SOURCE.index("options.Events.OnValidatePrincipal=", start)
        config = SOURCE[start:end]
        self.assertIn("options.Cookie.HttpOnly=true", config)
        self.assertIn("options.Cookie.SecurePolicy=CookieSecurePolicy.Always", config)
        self.assertIn("options.Cookie.SameSite=SameSiteMode.Strict", config)


if __name__ == "__main__":
    unittest.main()
