"""Regression guards for the isolated development-only PIN login.

Source checks are defense-in-depth and do not replace a deployed HTTP test.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "Program.cs").read_text(encoding="utf-8")


class LocalTestLoginGuards(unittest.TestCase):
    def test_pin_route_is_development_and_opt_in_only(self):
        route = SOURCE.index('app.MapPost("/api/account/test-login"')
        guard = SOURCE.rfind("if(app.Environment.IsDevelopment()", 0, route)
        self.assertGreaterEqual(guard, 0)
        segment = SOURCE[guard:route]
        self.assertIn('ANKA_ENABLE_LOCAL_TEST_LOGIN', segment)
        self.assertIn('StringComparison.OrdinalIgnoreCase', segment)

    def test_pin_route_rejects_remote_clients_and_hosts(self):
        start = SOURCE.index('app.MapPost("/api/account/test-login"')
        end = SOURCE.index('app.MapPost("/api/account/logout"', start)
        body = SOURCE[start:end]
        self.assertIn('IPAddress.IsLoopback(context.Connection.RemoteIpAddress', body)
        self.assertIn('IPAddress.IsLoopback(hostIp)', body)
        self.assertIn('SameOrigin(context.Request)', body)
        self.assertIn('input.Pin!="1234"', body)
        self.assertIn('.RequireRateLimiting("account")', body)

    def test_public_login_does_not_accept_test_pin(self):
        start = SOURCE.index('app.MapPost("/api/account/login"')
        end = SOURCE.index('if(app.Environment.IsDevelopment()', start)
        body = SOURCE[start:end]
        self.assertIn('AuthenticateAsync(', body)
        self.assertNotIn('1234', body)


if __name__ == "__main__":
    unittest.main()
