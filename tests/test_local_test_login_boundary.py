"""Regression guards for the opt-in development-only test login.

These static checks complement (but do not replace) HTTP integration tests.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class LocalTestLoginBoundaryTests(unittest.TestCase):
    def test_both_remote_address_and_requested_host_must_be_loopback(self):
        start = SOURCE.index('app.MapPost("/api/account/test-login"')
        end = SOURCE.index('app.MapPost("/api/account/logout"', start)
        route = SOURCE[start:end]
        self.assertIn("IPAddress.IsLoopback(context.Connection.RemoteIpAddress", route)
        self.assertIn('context.Request.Host.Host, "localhost"', route)
        self.assertIn("IPAddress.TryParse(context.Request.Host.Host, out var hostIp)", route)
        self.assertIn("IPAddress.IsLoopback(hostIp)", route)
        self.assertIn("return Results.StatusCode(403)", route)

    def test_test_login_needs_development_and_explicit_opt_in(self):
        start = SOURCE.index('app.MapPost("/api/account/test-login"')
        guard = SOURCE[max(0, start - 350):start]
        self.assertIn("app.Environment.IsDevelopment()", guard)
        self.assertIn('Environment.GetEnvironmentVariable("ANKA_ENABLE_LOCAL_TEST_LOGIN")', guard)
        self.assertIn("StringComparison.OrdinalIgnoreCase", guard)

    def test_test_login_cannot_register_accounts(self):
        start = SOURCE.index('app.MapPost("/api/account/test-login"')
        end = SOURCE.index('app.MapPost("/api/account/logout"', start)
        route = SOURCE[start:end]
        self.assertIn("FindLocalTestAccountAsync", route)
        self.assertNotIn("RegisterAsync", route)
        self.assertNotIn("CreateAccountAsync", route)


if __name__ == "__main__":
    unittest.main()
