"""Regression guards for the development-only fixed-PIN account lookup.

These source-level checks are defense-in-depth; production endpoint and browser
smoke tests remain mandatory before declaring the feature secure.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
BODY = SOURCE.split("FindLocalTestAccountAsync(", 1)[1].split("public async Task<IReadOnlyList<AnkaPublisherRequest>>", 1)[0]


class LocalTestLoginGuards(unittest.TestCase):
    def test_service_requires_development_and_explicit_opt_in(self):
        self.assertRegex(BODY, r"!env\.IsDevelopment\(\)")
        self.assertIn('ANKA_ENABLE_LOCAL_TEST_LOGIN', BODY)
        self.assertRegex(BODY, r"StringComparison\.OrdinalIgnoreCase")
        self.assertRegex(BODY, r"return null;")

    def test_lookup_rejects_disabled_and_privileged_accounts(self):
        match = re.search(r'cmd\.CommandText="(SELECT id,display_name,role FROM anka_users.*?)";', BODY, re.S)
        self.assertIsNotNone(match, "Expected parameterized account lookup")
        sql = match.group(1)
        self.assertRegex(sql, r"disabled\s*=\s*0")
        self.assertRegex(sql, r"role\s*=\s*'Reader'")
        self.assertRegex(sql, r"email\s*=\s*@email")
        self.assertIn('cmd.Parameters.AddWithValue("@email"', BODY)


if __name__ == "__main__":
    unittest.main()
