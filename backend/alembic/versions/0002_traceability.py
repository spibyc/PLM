"""QPLM 0.2 procurement-to-production traceability
Revision ID: 0002_traceability
Revises: 0001_initial
"""
from alembic import op
from app.models import Base
revision='0002_traceability'; down_revision='0001_initial'; branch_labels=None; depends_on=None
TABLES=['supplier','purchase_order','purchase_order_line','goods_receipt','goods_receipt_line','bom','bom_revision','bom_line','production_build','build_material','finished_serial']
IMMUTABLE_RELEASED=['bom_revision','bom_line','production_build','build_material','finished_serial','goods_receipt','goods_receipt_line']
def upgrade():
    bind=op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind,checkfirst=False)
    op.execute("INSERT INTO number_sequence (code,prefix,width,next_value) VALUES ('PO','PO-',6,1),('GRN','GRN-',6,1),('BOM','BOM-',6,1),('BUILD','BUILD-',6,1)")
    op.execute("""CREATE FUNCTION qplm_02_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_TABLE_NAME='bom_revision' AND OLD.status='Released' THEN RAISE EXCEPTION 'QPLM: Released BOM revisions are immutable'; END IF;
      IF TG_TABLE_NAME='bom_line' AND EXISTS (SELECT 1 FROM bom_revision r WHERE r.id=OLD.bom_revision_id AND r.status='Released') THEN RAISE EXCEPTION 'QPLM: Lines of a Released BOM are immutable'; END IF;
      IF TG_TABLE_NAME='production_build' AND OLD.status='Released' THEN RAISE EXCEPTION 'QPLM: Released builds are immutable'; END IF;
      IF TG_TABLE_NAME='build_material' AND EXISTS (SELECT 1 FROM production_build b WHERE b.id=OLD.build_id AND b.status='Released') THEN RAISE EXCEPTION 'QPLM: Material genealogy of a Released build is immutable'; END IF;
      IF TG_TABLE_NAME='finished_serial' AND OLD.status='Released' THEN RAISE EXCEPTION 'QPLM: Released serial records are immutable'; END IF;
      RETURN NEW; END $$""")
    for t in ['bom_revision','bom_line','production_build','build_material','finished_serial']:
        op.execute(f"CREATE TRIGGER trg_{t}_02_guard BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION qplm_02_guard()")
    for t in ['goods_receipt','goods_receipt_line']:
        op.execute(f"CREATE TRIGGER trg_{t}_append_only BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION qplm_append_only()")
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON supplier,purchase_order,purchase_order_line,bom,bom_revision,bom_line,production_build,build_material,finished_serial TO qplm_app")
    op.execute("GRANT SELECT,INSERT ON goods_receipt,goods_receipt_line TO qplm_app")
    op.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO qplm_app")
    # Controlled default-role permission expansion for the 0.2 modules.
    grants={
      "ADMIN":["supplier:read","po:read","bom:read","build:read"],
      "QUALITY":["supplier:read","po:read","bom:read","build:read","sign:supplier_approved","sign:bom_released","sign:build_released"],
      "ENGINEERING":["supplier:read","po:read","bom:read","bom:write","build:read","sign:bom_released"],
      "PURCHASING":["supplier:read","supplier:write","po:read","po:write","po:receive","bom:read","sign:po_approved"],
      "PRODUCTION":["supplier:read","po:read","bom:read","build:read","build:write"],
      "READONLY":["supplier:read","po:read","bom:read","build:read"]}
    for role,perms in grants.items():
        for perm in perms:
            op.execute(f"INSERT INTO role_permission(role_id,permission) SELECT id, '{perm}' FROM role WHERE code='{role}' ON CONFLICT DO NOTHING")
def downgrade():
    for t in reversed(TABLES): op.execute(f'DROP TABLE IF EXISTS {t} CASCADE')
    op.execute("DELETE FROM number_sequence WHERE code IN ('PO','GRN','BOM','BUILD')")
    op.execute('DROP FUNCTION IF EXISTS qplm_02_guard() CASCADE')
