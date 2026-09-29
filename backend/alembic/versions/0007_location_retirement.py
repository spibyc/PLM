"""Controlled location retirement and the Unallocated system location."""
from alembic import op
import sqlalchemy as sa

revision = "0007_location_retirement"
down_revision = "0006_document_control"
branch_labels = None
depends_on = None


def upgrade():
    # Fail before changing anything if this code already belongs to a physical location.
    # Never silently repurpose an installation's existing storage location.
    if op.get_bind().execute(sa.text("SELECT 1 FROM location WHERE code = 'UNALLOCATED'")).first():
        raise RuntimeError("UNALLOCATED is already a location code; resolve the code collision before migrating")
    op.add_column("location", sa.Column("system_key", sa.String(32), nullable=True))
    op.add_column("location", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_location_system_key", "location", ["system_key"])
    op.alter_column("location", "created_by", nullable=True)
    op.execute("""INSERT INTO location
        (id, kind, code, name, path, is_quarantine, is_active, system_key)
        VALUES (gen_random_uuid(), 'site', 'UNALLOCATED', 'Unallocated stock',
                'Unallocated stock', true, true, 'unallocated')""")
    op.execute("""INSERT INTO role_permission (role_id, permission)
        SELECT id, 'location:delete' FROM role WHERE code = 'ADMIN' ON CONFLICT DO NOTHING""")


def downgrade():
    # A used system location cannot be removed without destroying traceability.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM stock_txn t JOIN location l ON l.id=t.location_id
                   WHERE l.system_key IS NOT NULL)
        OR EXISTS (SELECT 1 FROM lot_balance b JOIN location l ON l.id=b.location_id
                   WHERE l.system_key IS NOT NULL)
        OR EXISTS (SELECT 1 FROM location WHERE retired_at IS NOT NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade after location retirement or Unallocated inventory use';
        END IF;
    END $$""")
    op.execute("ALTER TABLE location DISABLE TRIGGER trg_location_no_delete")
    op.execute("DELETE FROM location WHERE system_key = 'unallocated'")
    op.execute("ALTER TABLE location ENABLE TRIGGER trg_location_no_delete")
    op.drop_constraint("uq_location_system_key", "location", type_="unique")
    op.drop_column("location", "retired_at")
    op.drop_column("location", "system_key")
    op.alter_column("location", "created_by", nullable=False)
