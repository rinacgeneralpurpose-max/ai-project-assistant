"""Optional database integrity triggers for audit and requester provenance.

Migration prototype: no automatic execution, no production schema mutation.
A privileged database owner can drop triggers; restricted runtime grants are
also required. Existing records must be reviewed before installation.
"""
INTEGRITY_DDL = """
CREATE OR REPLACE FUNCTION reject_protected_row_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'protected records are append-only';
END;
$$;

DROP TRIGGER IF EXISTS protect_operation_audit_events ON operation_audit_events;
CREATE TRIGGER protect_operation_audit_events
BEFORE UPDATE OR DELETE ON operation_audit_events
FOR EACH ROW EXECUTE FUNCTION reject_protected_row_mutation();

DROP TRIGGER IF EXISTS protect_operation_requesters ON operation_requesters;
CREATE TRIGGER protect_operation_requesters
BEFORE UPDATE OR DELETE ON operation_requesters
FOR EACH ROW EXECUTE FUNCTION reject_protected_row_mutation();

DROP TRIGGER IF EXISTS protect_recovery_reviews ON recovery_reviews;
CREATE TRIGGER protect_recovery_reviews
BEFORE UPDATE OR DELETE ON recovery_reviews
FOR EACH ROW EXECUTE FUNCTION reject_protected_row_mutation();
"""
