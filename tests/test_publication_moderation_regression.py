"""Publication moderation regression guards.

These are source-level checks, not substitutes for SQLite/HTTP integration tests.
They guard against accidentally bypassing manual approval and live role checks.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")


def method(name, next_name):
    start = SOURCE.index("public async ", SOURCE.index(name) - 60)
    end = SOURCE.index("public async ", SOURCE.index(next_name) - 60)
    return SOURCE[start:end]


class PublicationModerationGuards(unittest.TestCase):
    def test_publisher_approval_is_transactional_and_pending_only(self):
        body = method("ReviewPublisherAsync(", "IsCurrentRoleAsync(")
        self.assertIn("BeginTransactionAsync()", body)
        self.assertIn("state='pending'", body)
        self.assertIn("applicant.role='Reader' AND applicant.disabled=0", body)
        self.assertIn("role='Publisher' WHERE id=@id AND role='Reader' AND disabled=0", body)
        self.assertIn("transaction.RollbackAsync()", body)
        self.assertIn("transaction.CommitAsync()", body)

    def test_book_approval_requires_live_admin_and_eligible_uploader(self):
        body = method("ReviewBookAsync(", "HasActiveAdminAsync(")
        for clause in (
            "state='pending'",
            "length(trim(rights_statement)) BETWEEN 12 AND 2000",
            "uploader.disabled=0",
            "uploader.role IN ('Publisher','Admin')",
            "reviewer.role='Admin' AND reviewer.disabled=0",
            "reviewed_by=@reviewer",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, body)

    def test_read_entitlement_cannot_override_unapproved_moderation(self):
        body = method("CanReadAsync(", "ShelfAsync(")
        moderation = "m.book_id=b.id AND m.state IS NOT 'approved'"
        self.assertIn(moderation, body)
        self.assertLess(body.index(moderation), body.index("anka_manual_entitlements"))
        self.assertIn("entitled_user.disabled=0", body)
        self.assertIn("u.role='Admin' AND u.disabled=0", body)


if __name__ == "__main__":
    unittest.main()
