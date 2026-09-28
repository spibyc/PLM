"""administrator superuser override

Revision ID: 0003_admin_superuser
Revises: 0002_traceability
"""
from alembic import op

revision = "0003_admin_superuser"
down_revision = "0002_traceability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Application DELETE is still protected by triggers. Only an application request that explicitly
    # enters the audited superuser path sets qplm.admin_override for its transaction.
    op.execute("GRANT DELETE ON item, item_revision, aml_entry, attachment, signature, state_transition TO qplm_app")
    op.execute("""CREATE OR REPLACE FUNCTION qplm_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF current_setting('qplm.admin_override', true) = 'on' THEN RETURN OLD; END IF;
      RAISE EXCEPTION 'QPLM: deletion from % is not permitted (controlled record)', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
    END $$;""")
    op.execute("""CREATE OR REPLACE FUNCTION qplm_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME <> 'audit_event' AND current_setting('qplm.admin_override', true) = 'on' THEN RETURN OLD; END IF;
      RAISE EXCEPTION 'QPLM: % on % is not permitted (append-only record)', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
    END $$;""")
    op.execute("""CREATE OR REPLACE FUNCTION qplm_item_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF current_setting('qplm.admin_override', true) = 'on' THEN RETURN NEW; END IF;
      IF OLD.status <> 'Draft' AND (
           NEW.item_id, NEW.revision_label, NEW.description, NEW.category, NEW.subcategory,
           NEW.component_type, NEW.value, NEW.package, NEW.rohs_status, NEW.reach_status,
           NEW.notes, NEW.change_reason, NEW.content_hash, NEW.created_by, NEW.created_at, NEW.supersedes_id
         ) IS DISTINCT FROM (
           OLD.item_id, OLD.revision_label, OLD.description, OLD.category, OLD.subcategory,
           OLD.component_type, OLD.value, OLD.package, OLD.rohs_status, OLD.reach_status,
           OLD.notes, OLD.change_reason, OLD.content_hash, OLD.created_by, OLD.created_at, OLD.supersedes_id
         ) THEN
        RAISE EXCEPTION 'QPLM: item revision % is % and its content cannot be changed', OLD.id, OLD.status
          USING ERRCODE = 'insufficient_privilege';
      END IF;
      IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
           (OLD.status, NEW.status) IN (
             ('Draft','Under Review'), ('Draft','Discarded'), ('Under Review','Draft'), ('Under Review','Approved'),
             ('Approved','Draft'), ('Approved','Released'), ('Released','Superseded'), ('Released','NRND'),
             ('Released','Obsolete'), ('Released','Prohibited'), ('NRND','Superseded'), ('NRND','Obsolete'),
             ('NRND','Prohibited'), ('Prohibited','Superseded'), ('Prohibited','Obsolete')
           )) THEN
        RAISE EXCEPTION 'QPLM: illegal revision state transition % -> %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$;""")
    op.execute("INSERT INTO role_permission(role_id, permission) SELECT id, 'admin:override' FROM role WHERE code='ADMIN' ON CONFLICT DO NOTHING")
    # Existing ADMIN installs predate the new all-permissions definition: synchronize them now.
    perms = ['users:admin','audit:read','item:read','item:write','aml:write','files:upload','files:verify','location:read','location:write','inventory:read','inventory:receive','inventory:transact','inventory:adjust','inventory:quarantine','sign:engineering_approved','sign:quality_approved','sign:released','sign:material_released','sign:aml_approved','supplier:read','supplier:write','po:read','po:write','po:receive','bom:read','bom:write','build:read','build:write','sign:supplier_approved','sign:po_approved','sign:bom_released','sign:build_released','admin:override']
    for p in perms:
        op.execute(f"INSERT INTO role_permission(role_id, permission) SELECT id, '{p}' FROM role WHERE code='ADMIN' ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission='admin:override'")
    op.execute("REVOKE DELETE ON item, item_revision, aml_entry, attachment, signature, state_transition FROM qplm_app")
