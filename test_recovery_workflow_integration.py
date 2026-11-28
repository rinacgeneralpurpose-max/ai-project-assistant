"""Opt-in real PostgreSQL recovery workflow tests on a disposable database ONLY.

Never use Render production DATABASE_URL or any production database.
Set RUN_POSTGRES_INTEGRATION_TESTS=1 and TEST_DATABASE_URL explicitly.
"""
import os
import threading
import unittest
from uuid import uuid4

from atomic_project_coordinator import AtomicProjectCoordinator
from authenticated_recovery_workflow import (
    AuthenticatedRecoveryWorkflow, REQUESTER_LINK_DDL,
)
from postgres_operation_coordinator import PostgresOperationCoordinator, SCHEMA_SQL
from postgres_project_gate import GATE_DDL
from recovery_review_store import RECOVERY_DDL, RecoveryReviewDenied

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg
    from psycopg.errors import UniqueViolation

AUDIENCE = "example-test-google-client.apps.googleusercontent.com"


def reviewer_claims(subject):
    return {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email_verified": True,
        "sub": subject,
    }


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL test DB and opt-in required")
class RecoveryDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "recovery_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(DSN, autocommit=True, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
                    cur.execute(GATE_DDL)
                    cur.execute(RECOVERY_DDL)
                    cur.execute(REQUESTER_LINK_DDL)
        except Exception:
            cls.admin.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        try:
            with cls.admin.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS " + cls.schema + " CASCADE")
        finally:
            cls.admin.close()

    def setUp(self):
        self.project = "P-" + uuid4().hex
        self.operation = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        coordinator = AtomicProjectCoordinator(self.conn)
        coordinator.start(project_id=self.project, operation_id=self.operation)
        coordinator.ambiguous(project_id=self.project, operation_id=self.operation)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO operation_requesters
                       (operation_id,requestor_subject) VALUES (%s,%s)""",
                    (self.operation, "requester-456"),
                )

    def workflow(self, conn=None, reviewer="reviewer-123"):
        return AuthenticatedRecoveryWorkflow(
            conn or self.conn,
            audience=AUDIENCE,
            allowed_reviewer_subjects={reviewer},
            verifier=lambda token, audience: reviewer_claims(reviewer),
        )

    def submit(self, workflow=None):
        return (workflow or self.workflow()).submit(
            token="offline-test-stub",
            project_id=self.project,
            operation_id=self.operation,
            evidence={"sheet_observation": "observed unchanged"},
            decision="hold",
        )

    def test_review_record_persists_and_gate_remains(self):
        result = self.submit()
        self.assertFalse(result["gate_released"])
        with psycopg.connect(DSN, options="-c search_path=" + self.schema) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT reviewer_id,decision FROM recovery_reviews WHERE operation_id=%s",
                    (self.operation,),
                )
                self.assertEqual(cur.fetchone(), ("reviewer-123", "hold"))
                cur.execute(
                    "SELECT recovery_required FROM project_write_gates WHERE project_id=%s",
                    (self.project,),
                )
                self.assertTrue(cur.fetchone()[0])

    def test_duplicate_review_uniqueness(self):
        self.submit()
        with self.assertRaises(UniqueViolation):
            self.submit()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM recovery_reviews WHERE operation_id=%s",
                (self.operation,),
            )
            self.assertEqual(cur.fetchone()[0], 1)

    def test_self_review_blocked_using_database_requester(self):
        with self.assertRaises(RecoveryReviewDenied):
            self.submit(self.workflow(reviewer="requester-456"))
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM recovery_reviews WHERE operation_id=%s",
                (self.operation,),
            )
            self.assertEqual(cur.fetchone()[0], 0)

    def test_review_failure_preserves_gate(self):
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """CREATE FUNCTION reject_recovery_review() RETURNS trigger
                       LANGUAGE plpgsql AS $$
                       BEGIN RAISE EXCEPTION 'review rejected'; END; $$"""
                )
                cur.execute(
                    """CREATE TRIGGER reject_recovery_review_insert
                       BEFORE INSERT ON recovery_reviews
                       FOR EACH ROW EXECUTE FUNCTION reject_recovery_review()"""
                )
        try:
            with self.assertRaises(Exception):
                self.submit()
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT recovery_required FROM project_write_gates WHERE project_id=%s",
                    (self.project,),
                )
                self.assertTrue(cur.fetchone()[0])
                cur.execute(
                    "SELECT COUNT(*) FROM recovery_reviews WHERE operation_id=%s",
                    (self.operation,),
                )
                self.assertEqual(cur.fetchone()[0], 0)
        finally:
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute("DROP TRIGGER reject_recovery_review_insert ON recovery_reviews")
                    cur.execute("DROP FUNCTION reject_recovery_review()")

    def test_concurrent_review_one_record_only(self):
        barrier = threading.Barrier(2)
        results = []

        def worker():
            try:
                with psycopg.connect(DSN, options="-c search_path=" + self.schema) as conn:
                    barrier.wait(timeout=10)
                    self.submit(self.workflow(conn=conn))
                results.append("recorded")
            except UniqueViolation:
                results.append("duplicate")
            except Exception as exc:
                results.append(type(exc).__name__)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(sorted(results), ["duplicate", "recorded"])
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM recovery_reviews WHERE operation_id=%s",
                (self.operation,),
            )
            self.assertEqual(cur.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
