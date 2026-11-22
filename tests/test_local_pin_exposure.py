"""Guard against accidental exposure of the fixed local test PIN in production.

This is a source-level regression guard, not a replacement for a deployed
Production HTTP smoke test. It never opens App_Data or EPUB assets.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class LocalTestLoginGuardTests(unittest.TestCase):
    def test_route_requires_development_and_explicit_opt_in(self):
        route = SOURCE.index('app.MapPost("/api/account/test-login"')
        prefix = SOURCE[max(0, route - 350):route]
        self.assertRegex(
            prefix,
            r'if\s*\(\s*app\.Environment\.IsDevelopment\(\)\s*&&'
        )
        self.assertIn('"ANKA_ENABLE_LOCAL_TEST_LOGIN"', prefix)
        self.assertIn('"true"', prefix)

    def test_test_login_rejects_non_loopback_connections_and_hosts(self):
        start = SOURCE.index('app.MapPost("/api/account/test-login"')
        end = SOURCE.index('app.MapPost("/api/account/logout"', start)
        handler = SOURCE[start:end]
        self.assertIn('IPAddress.IsLoopback(context.Connection.RemoteIpAddress', handler)
        self.assertIn('context.Request.Host.Host', handler)
        self.assertIn('IPAddress.IsLoopback(hostIp)', handler)
        self.assertIn('SameOrigin(context.Request)', handler)
        self.assertIn('input.Pin!="1234"', handler)
        self.assertIn('.RequireRateLimiting("account")', handler)

    def test_normal_login_does_not_use_fixed_pin(self):
        start = SOURCE.index('app.MapPost("/api/account/login"')
        end = SOURCE.index('app.MapPost("/api/account/test-login"', start)
        login = SOURCE[start:end]
        self.assertIn('accounts.AuthenticateAsync(', login)
        self.assertNotIn('input.Pin', login)
        self.assertNotIn('1234', login)


if __name__ == "__main__":
    unittest.main()
