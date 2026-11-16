"""Source-level security regressions; complement runtime authorization tests.

These checks deliberately fail if the local test PIN becomes available in
Production or a revoked role can keep an old authenticated cookie.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class AuthenticationBoundaryRegressionTests(unittest.TestCase):
    def test_test_pin_route_is_development_opt_in_only(self):
        route = SOURCE.index('app.MapPost("/api/account/test-login"')
        prefix = SOURCE[max(0, route - 350):route]
        self.assertRegex(
            prefix,
            r'if\s*\(\s*app\.Environment\.IsDevelopment\(\)\s*&&\s*'
            r'string\.Equals\(Environment\.GetEnvironmentVariable\("ANKA_ENABLE_LOCAL_TEST_LOGIN"\)',
        )
        body = SOURCE[route:SOURCE.index('app.MapPost("/api/account/logout"', route)]
        self.assertIn('IPAddress.IsLoopback', body)
        self.assertIn('SameOrigin(context.Request)', body)
        self.assertIn('input.Pin!="1234"', body)
        self.assertIn('.RequireRateLimiting("account")', body)

    def test_cookie_roles_revalidated_against_database(self):
        start = SOURCE.index('options.Events.OnValidatePrincipal=')
        end = SOURCE.index('options.Events.OnRedirectToLogin=', start)
        handler = SOURCE[start:end]
        self.assertIn('IsCurrentRoleAsync(id,role)', handler)
        self.assertIn('context.RejectPrincipal()', handler)
        self.assertIn('context.HttpContext.SignOutAsync', handler)

    def test_session_cookie_has_secure_defaults(self):
        self.assertIn('options.Cookie.HttpOnly=true', SOURCE)
        self.assertIn('options.Cookie.SecurePolicy=CookieSecurePolicy.Always', SOURCE)
        self.assertIn('options.Cookie.SameSite=SameSiteMode.Strict', SOURCE)

if __name__ == "__main__":
    unittest.main()
