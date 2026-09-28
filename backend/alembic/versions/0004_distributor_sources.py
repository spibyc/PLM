"""distributor purchasing sources
Revision ID: 0004_distributor_sources
Revises: 0003_admin_superuser
"""
from alembic import op
from app.models import Base
revision = "0004_distributor_sources"
down_revision = "0003_admin_superuser"
branch_labels = None
depends_on = None

def upgrade() -> None:
    Base.metadata.tables["distributor_source"].create(bind=op.get_bind(), checkfirst=False)
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON distributor_source TO qplm_app")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS distributor_source")
