"""Runtime SQLite regression for publisher application approval and revocation."""
import pathlib
import re
import sqlite3
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "AnkaAccountService.cs").read_text(encoding="utf-8")
BODY = SOURCE.split("public async Task<bool> ReviewPublisherAsync(", 1)[1].split("public async Task<bool> IsCurrentRoleAsync(", 1)[0]
REQUEST_SQL = re.search(r'cmd\.CommandText="(UPDATE anka_publisher_requests .*?)";', BODY, re.S).group(1)
ROLE_SQL = re.search(r'cmd\.CommandText="(UPDATE anka_users SET role=.*?)";', BODY, re.S).group(1)


class PublisherApprovalSqliteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE anka_users(id TEXT PRIMARY KEY,role TEXT,disabled INTEGER);
            CREATE TABLE anka_publisher_requests(user_id TEXT PRIMARY KEY,state TEXT,reviewed_utc TEXT);
            INSERT INTO anka_users VALUES
                ('reader','Reader',0),('disabled','Reader',1),
                ('publisher','Publisher',0),('admin','Admin',0);
            INSERT INTO anka_publisher_requests(user_id,state) VALUES
                ('reader','pending'),('disabled','pending'),
                ('publisher','pending'),('admin','pending');
        """)

    def tearDown(self):
        self.db.close()

    def decide(self, user_id, approve=True):
        state = "approved" if approve else "rejected"
        with self.db:
            result = self.db.execute(REQUEST_SQL, {"id": user_id, "state": state, "reviewer": "admin"})
            if result.rowcount != 1:
                return False
            if approve:
                changed = self.db.execute(ROLE_SQL, {"id": user_id})
                if changed.rowcount != 1:
                    raise RuntimeError("role update must roll back")
        return True

    def snapshot(self, user_id):
        return (
            self.db.execute("SELECT state,reviewed_utc FROM anka_publisher_requests WHERE user_id=?", (user_id,)).fetchone(),
            self.db.execute("SELECT role,disabled FROM anka_users WHERE id=?", (user_id,)).fetchone(),
        )

    def test_active_reader_can_be_approved(self):
        self.assertTrue(self.decide("reader"))
        self.assertEqual(self.snapshot("reader")[0][0], "approved")
        self.assertEqual(self.snapshot("reader")[1], ("Publisher", 0))

    def test_active_reader_can_be_rejected_without_role_change(self):
        self.assertTrue(self.decide("reader", approve=False))
        self.assertEqual(self.snapshot("reader")[0][0], "rejected")
        self.assertEqual(self.snapshot("reader")[1], ("Reader", 0))

    def test_disabled_and_already_promoted_accounts_cannot_be_reviewed(self):
        for user_id in ("disabled", "publisher", "admin"):
            for approve in (True, False):
                with self.subTest(user_id=user_id, approve=approve):
                    before = self.snapshot(user_id)
                    self.assertFalse(self.decide(user_id, approve))
                    self.assertEqual(self.snapshot(user_id), before)

    def test_revoked_applicant_cannot_be_reviewed(self):
        self.db.execute("UPDATE anka_users SET disabled=1 WHERE id='reader'")
        before = self.snapshot("reader")
        for approve in (True, False):
            self.assertFalse(self.decide("reader", approve))
            self.assertEqual(self.snapshot("reader"), before)

    def test_completed_request_cannot_be_reviewed_twice(self):
        self.assertTrue(self.decide("reader"))
        before = self.snapshot("reader")
        self.assertFalse(self.decide("reader", approve=False))
        self.assertEqual(self.snapshot("reader"), before)

    def test_role_update_failure_rolls_back_approval_and_audit(self):
        # Simulate a database failure after the request UPDATE but before role promotion.
        # The transaction must leave both the request and the user's role untouched.
        before = self.snapshot("reader")
        self.db.executescript("""
            CREATE TRIGGER prevent_publisher_promotion
            BEFORE UPDATE OF role ON anka_users
            WHEN NEW.id='reader' AND NEW.role='Publisher'
            BEGIN
                SELECT RAISE(ABORT, 'simulated role write failure');
            END;
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.decide("reader")
        self.assertEqual(self.snapshot("reader"), before)

    def test_deleted_applicant_cannot_be_approved_or_rejected(self):
        # An orphaned pending request must not be reviewed after its account is removed.
        self.db.execute("DELETE FROM anka_users WHERE id='reader'")
        before = self.snapshot("reader")
        for approve in (True, False):
            with self.subTest(approve=approve):
                self.assertFalse(self.decide("reader", approve))
                self.assertEqual(self.snapshot("reader"), before)

    def test_review_is_scoped_to_requested_applicant_only(self):
        # Approving one applicant must not alter unrelated pending requests.
        self.db.execute("INSERT INTO anka_users VALUES ('second','Reader',0)")
        self.db.execute("INSERT INTO anka_publisher_requests(user_id,state) VALUES ('second','pending')")
        unrelated_before = {
            user_id: self.snapshot(user_id)
            for user_id in ("second", "disabled", "publisher", "admin")
        }
        self.assertTrue(self.decide("reader"))
        self.assertEqual(self.snapshot("reader")[0][0], "approved")
        for user_id, before in unrelated_before.items():
            with self.subTest(user_id=user_id):
                self.assertEqual(self.snapshot(user_id), before)

    def test_rejection_does_not_change_other_pending_requests(self):
        self.db.execute("INSERT INTO anka_users VALUES ('second','Reader',0)")
        self.db.execute("INSERT INTO anka_publisher_requests(user_id,state) VALUES ('second','pending')")
        other_before = self.snapshot("second")
        self.assertTrue(self.decide("reader", approve=False))
        self.assertEqual(self.snapshot("reader")[0][0], "rejected")
        self.assertEqual(self.snapshot("reader")[1], ("Reader", 0))
        self.assertEqual(self.snapshot("second"), other_before)

    def test_forged_identifiers_do_not_change_requests(self):
        before = self.snapshot("reader")
        for forged in ("reader' OR 1=1 --", "'; DROP TABLE anka_users; --", "READER", ""):
            with self.subTest(forged=forged):
                self.assertFalse(self.decide(forged))
                self.assertEqual(self.snapshot("reader"), before)


if __name__ == "__main__":
    unittest.main()
