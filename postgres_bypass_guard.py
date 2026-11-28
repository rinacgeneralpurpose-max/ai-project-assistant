"""Opt-in PostgreSQL migration SQL that blocks legacy coordinator write-state bypass.

Requires sheet_operations, project_write_gates, operation_audit_events.
Apply via reviewed migration only; no production migration is run here.
"""

BYPASS_GUARD_DDL = """
CREATE OR REPLACE FUNCTION enforce_sheet_operation_gate()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state = 'applying' AND OLD.state IS DISTINCT FROM 'applying' THEN
        IF NOT EXISTS (
            SELECT 1 FROM project_write_gates g
            WHERE g.project_id=NEW.project_id
              AND g.operation_id=NEW.operation_id
              AND g.recovery_required=FALSE
        ) THEN
            RAISE EXCEPTION 'applying requires owned project gate';
        END IF;
    END IF;

    IF NEW.state = 'reconciliation_required'
       AND OLD.state IS DISTINCT FROM 'reconciliation_required' THEN
        IF NOT EXISTS (
            SELECT 1 FROM project_write_gates g
            WHERE g.project_id=NEW.project_id
              AND g.operation_id=NEW.operation_id
              AND g.recovery_required=TRUE
        ) THEN
            RAISE EXCEPTION 'reconciliation requires recovery gate';
        END IF;
    END IF;

    -- No confirmed-success path is safe without audited release and
    -- external Google Sheets in-flight request fencing.
    IF NEW.state = 'applied' AND OLD.state IS DISTINCT FROM 'applied' THEN
        RAISE EXCEPTION 'applied transition disabled pending safe release';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS enforce_sheet_operation_gate_trigger ON sheet_operations;
CREATE CONSTRAINT TRIGGER enforce_sheet_operation_gate_trigger
AFTER UPDATE OF state ON sheet_operations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION enforce_sheet_operation_gate();

CREATE OR REPLACE FUNCTION enforce_sheet_operation_audit()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    required_event TEXT;
BEGIN
    IF NEW.state = 'applying' AND OLD.state IS DISTINCT FROM 'applying' THEN
        required_event := 'operation_started';
    ELSIF NEW.state = 'reconciliation_required'
          AND OLD.state IS DISTINCT FROM 'reconciliation_required' THEN
        required_event := 'reconciliation_required';
    ELSE
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM operation_audit_events a
        WHERE a.operation_id=NEW.operation_id AND a.event_type=required_event
    ) THEN
        RAISE EXCEPTION 'missing required operation audit event: %', required_event;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS enforce_sheet_operation_audit_trigger ON sheet_operations;
CREATE CONSTRAINT TRIGGER enforce_sheet_operation_audit_trigger
AFTER UPDATE OF state ON sheet_operations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION enforce_sheet_operation_audit();
"""
