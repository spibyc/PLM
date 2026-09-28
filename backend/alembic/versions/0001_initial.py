"""initial schema

Revision ID: 0001_initial
Revises: 
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Data-integrity controls enforced by the database itself (defence in depth).
# These apply to every role, including the application role.
# ---------------------------------------------------------------------------
APPEND_ONLY = ("audit_event", "signature", "state_transition", "stock_txn", "attachment")
NO_DELETE = (
    "app_user", "role", "user_role", "role_permission", "item", "item_revision", "manufacturer",
    "manufacturer_part", "aml_entry", "file_object", "location", "inventory_lot", "lot_balance",
    "number_sequence",
)

CONTROL_SQL = [
    """
    CREATE FUNCTION qplm_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'QPLM: % on % is not permitted (append-only record)', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
    END $$;
    """,
    """
    CREATE FUNCTION qplm_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'QPLM: deletion from % is not permitted (controlled record)', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
    END $$;
    """,
    *[
        f"CREATE TRIGGER trg_{t}_append_only BEFORE UPDATE OR DELETE ON {t} "
        f"FOR EACH ROW EXECUTE FUNCTION qplm_append_only()"
        for t in APPEND_ONLY
    ],
    *[
        f"CREATE TRIGGER trg_{t}_no_truncate BEFORE TRUNCATE ON {t} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION qplm_append_only()"
        for t in APPEND_ONLY
    ],
    *[
        f"CREATE TRIGGER trg_{t}_no_delete BEFORE DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION qplm_no_delete()"
        for t in NO_DELETE
    ],
    # Item revisions: content is frozen once the revision leaves Draft; status moves only along permitted edges.
    """
    CREATE FUNCTION qplm_item_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
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
             ('Draft','Under Review'), ('Draft','Discarded'),
             ('Under Review','Draft'), ('Under Review','Approved'),
             ('Approved','Draft'), ('Approved','Released'),
             ('Released','Superseded'), ('Released','NRND'), ('Released','Obsolete'), ('Released','Prohibited'),
             ('NRND','Superseded'), ('NRND','Obsolete'), ('NRND','Prohibited'),
             ('Prohibited','Superseded'), ('Prohibited','Obsolete')
           )) THEN
        RAISE EXCEPTION 'QPLM: illegal revision state transition % -> %', OLD.status, NEW.status
          USING ERRCODE = 'check_violation';
      END IF;
      RETURN NEW;
    END $$;
    """,
    "CREATE TRIGGER trg_item_revision_guard BEFORE UPDATE ON item_revision "
    "FOR EACH ROW EXECUTE FUNCTION qplm_item_revision_guard()",
    # Lots: provenance immutable; only status may change.
    """
    CREATE FUNCTION qplm_lot_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (NEW.id, NEW.lot_no, NEW.item_id, NEW.item_revision_id, NEW.manufacturer_part_id, NEW.supplier_name,
          NEW.supplier_part_number, NEW.purchase_order_ref, NEW.supplier_lot, NEW.manufacturer_lot, NEW.date_code,
          NEW.qty_received, NEW.expiry_date, NEW.received_at, NEW.received_by, NEW.notes)
         IS DISTINCT FROM
         (OLD.id, OLD.lot_no, OLD.item_id, OLD.item_revision_id, OLD.manufacturer_part_id, OLD.supplier_name,
          OLD.supplier_part_number, OLD.purchase_order_ref, OLD.supplier_lot, OLD.manufacturer_lot, OLD.date_code,
          OLD.qty_received, OLD.expiry_date, OLD.received_at, OLD.received_by, OLD.notes) THEN
        RAISE EXCEPTION 'QPLM: lot provenance is immutable (lot %)', OLD.lot_no
          USING ERRCODE = 'insufficient_privilege';
      END IF;
      RETURN NEW;
    END $$;
    """,
    "CREATE TRIGGER trg_inventory_lot_guard BEFORE UPDATE ON inventory_lot "
    "FOR EACH ROW EXECUTE FUNCTION qplm_lot_guard()",
    # Files may only be attached to an item revision while it is Draft.
    """
    CREATE FUNCTION qplm_attachment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE st text;
    BEGIN
      IF NEW.object_type = 'item_revision' THEN
        SELECT status INTO st FROM item_revision WHERE id = NEW.object_id;
        IF st IS NULL THEN RAISE EXCEPTION 'QPLM: item revision % not found', NEW.object_id; END IF;
        IF st <> 'Draft' THEN
          RAISE EXCEPTION 'QPLM: cannot attach files to a % revision', st USING ERRCODE = 'insufficient_privilege';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    """,
    "CREATE TRIGGER trg_attachment_guard BEFORE INSERT ON attachment "
    "FOR EACH ROW EXECUTE FUNCTION qplm_attachment_guard()",
    # Search support
    "CREATE INDEX ix_item_revision_desc_trgm ON item_revision USING gin (description gin_trgm_ops)",
    "CREATE INDEX ix_item_pn_trgm ON item USING gin (part_number gin_trgm_ops)",
    "CREATE INDEX ix_mpn_trgm ON manufacturer_part USING gin ((mpn::text) gin_trgm_ops)",
    # Number sequences
    "INSERT INTO number_sequence (code, prefix, width, next_value) VALUES "
    "('PART','PN-',6,1), ('LOT','LOT-',6,1)",
    # Least-privilege application role: no DELETE anywhere, no UPDATE on append-only tables, no DDL.
    """
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qplm_app') THEN
        CREATE ROLE qplm_app NOLOGIN;
      END IF;
    END $$;
    """,
    "GRANT USAGE ON SCHEMA public TO qplm_app",
    "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO qplm_app",
    "REVOKE INSERT, UPDATE ON alembic_version FROM qplm_app",
    *[f"REVOKE UPDATE ON {t} FROM qplm_app" for t in APPEND_ONLY],
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO qplm_app",
]

DROP_CONTROL_SQL = [
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM qplm_app",
    "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM qplm_app",
    "DROP TRIGGER IF EXISTS trg_attachment_guard ON attachment",
    "DROP TRIGGER IF EXISTS trg_inventory_lot_guard ON inventory_lot",
    "DROP TRIGGER IF EXISTS trg_item_revision_guard ON item_revision",
    *[f"DROP TRIGGER IF EXISTS trg_{t}_append_only ON {t}" for t in APPEND_ONLY],
    *[f"DROP TRIGGER IF EXISTS trg_{t}_no_truncate ON {t}" for t in APPEND_ONLY],
    *[f"DROP TRIGGER IF EXISTS trg_{t}_no_delete ON {t}" for t in NO_DELETE],
    "DROP FUNCTION IF EXISTS qplm_attachment_guard()",
    "DROP FUNCTION IF EXISTS qplm_lot_guard()",
    "DROP FUNCTION IF EXISTS qplm_item_revision_guard()",
    "DROP FUNCTION IF EXISTS qplm_no_delete()",
    "DROP FUNCTION IF EXISTS qplm_append_only()",
]


def upgrade() -> None:
    for ext in ("citext", "pg_trgm", "pgcrypto"):
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
    # ### commands auto generated by Alembic (reviewed) ###
    op.create_table('app_user',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', postgresql.CITEXT(), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_user')),
    sa.UniqueConstraint('username', name=op.f('uq_app_user_username'))
    )
    op.create_table('manufacturer',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', postgresql.CITEXT(), nullable=False),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_manufacturer')),
    sa.UniqueConstraint('name', name=op.f('uq_manufacturer_name'))
    )
    op.create_table('number_sequence',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('prefix', sa.String(length=32), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('next_value', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_number_sequence')),
    sa.UniqueConstraint('prefix', name=op.f('uq_number_sequence_prefix'))
    )
    op.create_table('role',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_role')),
    sa.UniqueConstraint('code', name=op.f('uq_role_code'))
    )
    op.create_table('audit_event',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('event_uuid', sa.UUID(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_username', sa.String(length=200), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=400), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('entity_label', sa.String(length=300), nullable=True),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('prev_hash', sa.String(length=64), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_audit_event_actor_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_event')),
    sa.UniqueConstraint('event_uuid', name=op.f('uq_audit_event_event_uuid'))
    )
    op.create_index('ix_audit_actor', 'audit_event', ['actor_id'], unique=False)
    op.create_index('ix_audit_entity', 'audit_event', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_audit_occurred', 'audit_event', ['occurred_at'], unique=False)
    op.create_table('file_object',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('mime_type', sa.String(length=200), nullable=False),
    sa.Column('storage_backend', sa.String(length=16), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_verify_result', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_file_object_created_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_file_object')),
    sa.UniqueConstraint('sha256', name=op.f('uq_file_object_sha256'))
    )
    op.create_table('item',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('part_number', sa.String(length=64), nullable=False),
    sa.Column('item_class', sa.String(length=32), nullable=False),
    sa.Column('uom', sa.String(length=8), nullable=False),
    sa.Column('min_stock', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('current_released_revision_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.CheckConstraint("item_class IN ('component','bare_pcb','pcba','mechanical','cable','firmware','assembly','product')", name=op.f('ck_item_item_class')),
    sa.CheckConstraint("uom IN ('pcs','m','g','ml','kg','l')", name=op.f('ck_item_uom')),
    sa.CheckConstraint('min_stock >= 0', name=op.f('ck_item_min_stock')),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_item_created_by_app_user')),
    sa.ForeignKeyConstraint(['current_released_revision_id'], ['item_revision.id'], name='fk_item_current_rev', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_item')),
    sa.UniqueConstraint('part_number', name=op.f('uq_item_part_number'))
    )
    op.create_table('location',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('path', sa.String(length=1000), nullable=False),
    sa.Column('is_quarantine', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9-]*$'", name=op.f('ck_location_code_format')),
    sa.CheckConstraint("kind IN ('site','room','cabinet','drawer','bin','compartment')", name=op.f('ck_location_kind')),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_location_created_by_app_user')),
    sa.ForeignKeyConstraint(['parent_id'], ['location.id'], name=op.f('fk_location_parent_id_location')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_location')),
    sa.UniqueConstraint('code', name=op.f('uq_location_code'))
    )
    op.create_index(op.f('ix_location_parent_id'), 'location', ['parent_id'], unique=False)
    op.create_table('manufacturer_part',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('manufacturer_id', sa.UUID(), nullable=False),
    sa.Column('mpn', postgresql.CITEXT(), nullable=False),
    sa.Column('lifecycle', sa.String(length=32), nullable=False),
    sa.Column('datasheet_url', sa.String(length=500), nullable=True),
    sa.Column('rohs_status', sa.String(length=32), nullable=True),
    sa.Column('reach_status', sa.String(length=32), nullable=True),
    sa.Column('country_of_origin', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.CheckConstraint("lifecycle IN ('Unknown','Active','NRND','Last Time Buy','EOL','Obsolete')", name=op.f('ck_manufacturer_part_lifecycle')),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturer.id'], name=op.f('fk_manufacturer_part_manufacturer_id_manufacturer')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_manufacturer_part')),
    sa.UniqueConstraint('manufacturer_id', 'mpn', name=op.f('uq_manufacturer_part_manufacturer_id_mpn'))
    )
    op.create_table('role_permission',
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('permission', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['role.id'], name=op.f('fk_role_permission_role_id_role')),
    sa.PrimaryKeyConstraint('role_id', 'permission', name=op.f('pk_role_permission'))
    )
    op.create_table('signature',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('object_type', sa.String(length=64), nullable=False),
    sa.Column('object_id', sa.UUID(), nullable=False),
    sa.Column('review_cycle', sa.Integer(), nullable=False),
    sa.Column('meaning', sa.String(length=64), nullable=False),
    sa.Column('signer_id', sa.UUID(), nullable=False),
    sa.Column('signer_name', sa.String(length=200), nullable=False),
    sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('auth_method', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['signer_id'], ['app_user.id'], name=op.f('fk_signature_signer_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signature')),
    sa.UniqueConstraint('object_type', 'object_id', 'review_cycle', 'meaning', 'signer_id', name=op.f('uq_signature_object_type_object_id_review_cycle_meaning_signer_id'))
    )
    op.create_index('ix_signature_object', 'signature', ['object_type', 'object_id'], unique=False)
    op.create_table('user_role',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('granted_by', sa.UUID(), nullable=True),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['granted_by'], ['app_user.id'], name=op.f('fk_user_role_granted_by_app_user')),
    sa.ForeignKeyConstraint(['revoked_by'], ['app_user.id'], name=op.f('fk_user_role_revoked_by_app_user')),
    sa.ForeignKeyConstraint(['role_id'], ['role.id'], name=op.f('fk_user_role_role_id_role')),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_user_role_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_role'))
    )
    op.create_table('user_session',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=400), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_user_session_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_session')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_session_token_hash'))
    )
    op.create_index(op.f('ix_user_session_user_id'), 'user_session', ['user_id'], unique=False)
    op.create_table('aml_entry',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('manufacturer_part_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('preferred', sa.Boolean(), nullable=False),
    sa.Column('qualification_status', sa.String(length=64), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.UUID(), nullable=True),
    sa.CheckConstraint("status IN ('Proposed','Approved','Disqualified')", name=op.f('ck_aml_entry_status')),
    sa.ForeignKeyConstraint(['approved_by'], ['app_user.id'], name=op.f('fk_aml_entry_approved_by_app_user')),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_aml_entry_created_by_app_user')),
    sa.ForeignKeyConstraint(['item_id'], ['item.id'], name=op.f('fk_aml_entry_item_id_item')),
    sa.ForeignKeyConstraint(['manufacturer_part_id'], ['manufacturer_part.id'], name=op.f('fk_aml_entry_manufacturer_part_id_manufacturer_part')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_aml_entry')),
    sa.UniqueConstraint('item_id', 'manufacturer_part_id', name=op.f('uq_aml_entry_item_id_manufacturer_part_id'))
    )
    op.create_index(op.f('ix_aml_entry_item_id'), 'aml_entry', ['item_id'], unique=False)
    op.create_table('attachment',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('object_type', sa.String(length=64), nullable=False),
    sa.Column('object_id', sa.UUID(), nullable=False),
    sa.Column('file_object_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('doc_kind', sa.String(length=64), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('uploaded_by', sa.UUID(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.ForeignKeyConstraint(['file_object_id'], ['file_object.id'], name=op.f('fk_attachment_file_object_id_file_object')),
    sa.ForeignKeyConstraint(['uploaded_by'], ['app_user.id'], name=op.f('fk_attachment_uploaded_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attachment'))
    )
    op.create_index('ix_attachment_object', 'attachment', ['object_type', 'object_id'], unique=False)
    op.create_table('item_revision',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('revision_label', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('review_cycle', sa.Integer(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('subcategory', sa.String(length=100), nullable=True),
    sa.Column('component_type', sa.String(length=100), nullable=True),
    sa.Column('value', sa.String(length=100), nullable=True),
    sa.Column('package', sa.String(length=100), nullable=True),
    sa.Column('rohs_status', sa.String(length=32), nullable=True),
    sa.Column('reach_status', sa.String(length=32), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('change_reason', sa.Text(), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('supersedes_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('modified_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('modified_by', sa.UUID(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('Draft','Under Review','Approved','Released','NRND','Obsolete','Prohibited','Superseded','Discarded')", name=op.f('ck_item_revision_status')),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_item_revision_created_by_app_user')),
    sa.ForeignKeyConstraint(['item_id'], ['item.id'], name=op.f('fk_item_revision_item_id_item')),
    sa.ForeignKeyConstraint(['modified_by'], ['app_user.id'], name=op.f('fk_item_revision_modified_by_app_user')),
    sa.ForeignKeyConstraint(['supersedes_id'], ['item_revision.id'], name=op.f('fk_item_revision_supersedes_id_item_revision')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_item_revision')),
    sa.UniqueConstraint('item_id', 'revision_label', name=op.f('uq_item_revision_item_id_revision_label'))
    )
    op.create_index(op.f('ix_item_revision_item_id'), 'item_revision', ['item_id'], unique=False)
    op.create_index('uq_item_revision_one_open', 'item_revision', ['item_id'], unique=True, postgresql_where=sa.text("status IN ('Draft','Under Review','Approved')"))
    op.create_table('state_transition',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('object_type', sa.String(length=64), nullable=False),
    sa.Column('object_id', sa.UUID(), nullable=False),
    sa.Column('from_status', sa.String(length=32), nullable=True),
    sa.Column('to_status', sa.String(length=32), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('signature_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_state_transition_actor_id_app_user')),
    sa.ForeignKeyConstraint(['signature_id'], ['signature.id'], name=op.f('fk_state_transition_signature_id_signature')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_state_transition'))
    )
    op.create_index('ix_transition_object', 'state_transition', ['object_type', 'object_id'], unique=False)
    op.create_table('inventory_lot',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lot_no', sa.String(length=64), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('item_revision_id', sa.UUID(), nullable=False),
    sa.Column('manufacturer_part_id', sa.UUID(), nullable=True),
    sa.Column('supplier_name', sa.String(length=200), nullable=True),
    sa.Column('supplier_part_number', sa.String(length=100), nullable=True),
    sa.Column('purchase_order_ref', sa.String(length=64), nullable=True),
    sa.Column('supplier_lot', sa.String(length=100), nullable=True),
    sa.Column('manufacturer_lot', sa.String(length=100), nullable=True),
    sa.Column('date_code', sa.String(length=32), nullable=True),
    sa.Column('qty_received', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('expiry_date', sa.Date(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('received_by', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('Pending Inspection','Available','Quarantined')", name=op.f('ck_inventory_lot_status')),
    sa.CheckConstraint('qty_received > 0', name=op.f('ck_inventory_lot_qty_received')),
    sa.ForeignKeyConstraint(['item_id'], ['item.id'], name=op.f('fk_inventory_lot_item_id_item')),
    sa.ForeignKeyConstraint(['item_revision_id'], ['item_revision.id'], name=op.f('fk_inventory_lot_item_revision_id_item_revision')),
    sa.ForeignKeyConstraint(['manufacturer_part_id'], ['manufacturer_part.id'], name=op.f('fk_inventory_lot_manufacturer_part_id_manufacturer_part')),
    sa.ForeignKeyConstraint(['received_by'], ['app_user.id'], name=op.f('fk_inventory_lot_received_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_lot')),
    sa.UniqueConstraint('lot_no', name=op.f('uq_inventory_lot_lot_no'))
    )
    op.create_index(op.f('ix_inventory_lot_item_id'), 'inventory_lot', ['item_id'], unique=False)
    op.create_table('lot_balance',
    sa.Column('lot_id', sa.UUID(), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=False),
    sa.Column('qty_on_hand', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('qty_reserved', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.CheckConstraint('qty_on_hand >= 0', name=op.f('ck_lot_balance_on_hand_nonneg')),
    sa.CheckConstraint('qty_reserved <= qty_on_hand', name=op.f('ck_lot_balance_reserved_le_on_hand')),
    sa.CheckConstraint('qty_reserved >= 0', name=op.f('ck_lot_balance_reserved_nonneg')),
    sa.ForeignKeyConstraint(['location_id'], ['location.id'], name=op.f('fk_lot_balance_location_id_location')),
    sa.ForeignKeyConstraint(['lot_id'], ['inventory_lot.id'], name=op.f('fk_lot_balance_lot_id_inventory_lot')),
    sa.PrimaryKeyConstraint('lot_id', 'location_id', name=op.f('pk_lot_balance'))
    )
    op.create_index('ix_lot_balance_location', 'lot_balance', ['location_id'], unique=False)
    op.create_table('stock_txn',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('txn_uuid', sa.UUID(), nullable=False),
    sa.Column('correlation_id', sa.UUID(), nullable=False),
    sa.Column('txn_type', sa.String(length=32), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=False),
    sa.Column('lot_id', sa.UUID(), nullable=False),
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=True),
    sa.Column('d_on_hand', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('d_reserved', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('on_hand_before', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('on_hand_after', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('reserved_before', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('reserved_after', sa.Numeric(precision=18, scale=6), nullable=False),
    sa.Column('reason', sa.String(length=200), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('reference', sa.String(length=100), nullable=True),
    sa.Column('corrects_txn_id', sa.BigInteger(), nullable=True),
    sa.Column('signature_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("txn_type IN ('RECEIPT','ISSUE','RETURN','RESERVE','RESERVE_RELEASE','TRANSFER_OUT','TRANSFER_IN','ADJUST','SCRAP','QUARANTINE','QUARANTINE_RELEASE','INSPECTION_ACCEPT','INSPECTION_REJECT')", name=op.f('ck_stock_txn_txn_type')),
    sa.CheckConstraint('on_hand_after = on_hand_before + d_on_hand', name=op.f('ck_stock_txn_on_hand_arith')),
    sa.CheckConstraint('on_hand_after >= 0 AND reserved_after >= 0', name=op.f('ck_stock_txn_nonneg')),
    sa.CheckConstraint('reserved_after = reserved_before + d_reserved', name=op.f('ck_stock_txn_reserved_arith')),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_stock_txn_actor_id_app_user')),
    sa.ForeignKeyConstraint(['corrects_txn_id'], ['stock_txn.id'], name=op.f('fk_stock_txn_corrects_txn_id_stock_txn')),
    sa.ForeignKeyConstraint(['item_id'], ['item.id'], name=op.f('fk_stock_txn_item_id_item')),
    sa.ForeignKeyConstraint(['location_id'], ['location.id'], name=op.f('fk_stock_txn_location_id_location')),
    sa.ForeignKeyConstraint(['lot_id'], ['inventory_lot.id'], name=op.f('fk_stock_txn_lot_id_inventory_lot')),
    sa.ForeignKeyConstraint(['signature_id'], ['signature.id'], name=op.f('fk_stock_txn_signature_id_signature')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stock_txn')),
    sa.UniqueConstraint('txn_uuid', name=op.f('uq_stock_txn_txn_uuid'))
    )
    op.create_index(op.f('ix_stock_txn_correlation_id'), 'stock_txn', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_stock_txn_item_id'), 'stock_txn', ['item_id'], unique=False)
    op.create_index(op.f('ix_stock_txn_lot_id'), 'stock_txn', ['lot_id'], unique=False)
    op.create_index('ix_stock_txn_occurred', 'stock_txn', ['occurred_at'], unique=False)
    # ### end Alembic commands ###
    for stmt in CONTROL_SQL:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DROP_CONTROL_SQL:
        op.execute(stmt)
    # ### commands auto generated by Alembic (reviewed) ###
    op.drop_index('ix_stock_txn_occurred', table_name='stock_txn')
    op.drop_index(op.f('ix_stock_txn_lot_id'), table_name='stock_txn')
    op.drop_index(op.f('ix_stock_txn_item_id'), table_name='stock_txn')
    op.drop_index(op.f('ix_stock_txn_correlation_id'), table_name='stock_txn')
    op.drop_table('stock_txn')
    op.drop_index('ix_lot_balance_location', table_name='lot_balance')
    op.drop_table('lot_balance')
    op.drop_index(op.f('ix_inventory_lot_item_id'), table_name='inventory_lot')
    op.drop_table('inventory_lot')
    op.drop_index('ix_transition_object', table_name='state_transition')
    op.drop_table('state_transition')
    op.drop_index('uq_item_revision_one_open', table_name='item_revision', postgresql_where=sa.text("status IN ('Draft','Under Review','Approved')"))
    op.drop_index(op.f('ix_item_revision_item_id'), table_name='item_revision')
    op.drop_table('item_revision')
    op.drop_index('ix_attachment_object', table_name='attachment')
    op.drop_table('attachment')
    op.drop_index(op.f('ix_aml_entry_item_id'), table_name='aml_entry')
    op.drop_table('aml_entry')
    op.drop_index(op.f('ix_user_session_user_id'), table_name='user_session')
    op.drop_table('user_session')
    op.drop_table('user_role')
    op.drop_index('ix_signature_object', table_name='signature')
    op.drop_table('signature')
    op.drop_table('role_permission')
    op.drop_table('manufacturer_part')
    op.drop_index(op.f('ix_location_parent_id'), table_name='location')
    op.drop_table('location')
    op.drop_table('item')
    op.drop_table('file_object')
    op.drop_index('ix_audit_occurred', table_name='audit_event')
    op.drop_index('ix_audit_entity', table_name='audit_event')
    op.drop_index('ix_audit_actor', table_name='audit_event')
    op.drop_table('audit_event')
    op.drop_table('role')
    op.drop_table('number_sequence')
    op.drop_table('manufacturer')
    op.drop_table('app_user')
    # ### end Alembic commands ###
