"""Source-level publisher approval invariants; runtime SQLite tests still required."""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")


class PublisherApprovalRegressionTests(unittest.TestCase):
    def test_no_legacy_direct_promotion_entry_point(self):
        self.assertNotIn("MakePublisherAsync(", SOURCE)

    def test_approval_and_role_change_share_transaction(self):
        start = SOURCE.index("public async Task<bool> ReviewPublisherAsync(")
        end = SOURCE.index("public async Task<bool> IsCurrentRoleAsync(", start)
        body = SOURCE[start:end]
        self.assertIn("BeginTransactionAsync()", body)
        self.assertIn("cmd.Transaction=(SqliteTransaction)transaction", body)
        self.assertIn("state='pending'", body)
        self.assertIn("role='Publisher'", body)
        self.assertIn("role='Reader' AND disabled=0", body)
        self.assertIn("transaction.RollbackAsync()", body)
        self.assertIn("transaction.CommitAsync()", body)
        self.assertLess(body.index("role='Publisher'"), body.index("transaction.CommitAsync()"))
        self.assertRegex(body, r"if\s*\(await cmd\.ExecuteNonQueryAsync\(\)!=1\)\s*\{\s*await transaction\.RollbackAsync\(\)")

    def test_session_role_lookup_rejects_disabled_accounts(self):
        start = SOURCE.index("public async Task<bool> IsCurrentRoleAsync(")
        end = SOURCE.index("public async Task<bool> RecordBookSubmissionAsync(", start)
        self.assertIn("role=@role AND disabled=0", SOURCE[start:end])


if __name__ == "__main__":
    unittest.main()
