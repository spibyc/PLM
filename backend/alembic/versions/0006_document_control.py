"""controlled document register and revision history
Revision ID: 0006_document_control
Revises: 0005_supplier_workflow
"""
from alembic import op
from app.models import Base
revision="0006_document_control"; down_revision="0005_supplier_workflow"; branch_labels=None; depends_on=None
def upgrade():
    Base.metadata.tables["controlled_document"].create(bind=op.get_bind(),checkfirst=False)
    Base.metadata.tables["document_revision"].create(bind=op.get_bind(),checkfirst=False)
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON controlled_document,document_revision TO qplm_app")
    # Existing installations deliberately do not have bootstrap mutate roles. Grant the new
    # document permissions explicitly as part of this controlled release.
    grants={
      "ADMIN":["document:read","document:write","document:upload","sign:document_released","sign:document_obsolete"],
      "QUALITY":["document:read","document:write","document:upload","sign:document_released","sign:document_obsolete"],
      "ENGINEERING":["document:read","document:write","document:upload"],
      "PURCHASING":["document:read"],"PRODUCTION":["document:read"],"READONLY":["document:read"]}
    for role,perms in grants.items():
        for perm in perms:
            op.execute(f"INSERT INTO role_permission (role_id, permission) SELECT id, '{perm}' FROM role WHERE code='{role}' ON CONFLICT DO NOTHING")
def downgrade():
    op.execute("DROP TABLE IF EXISTS document_revision")
    op.execute("DROP TABLE IF EXISTS controlled_document")
