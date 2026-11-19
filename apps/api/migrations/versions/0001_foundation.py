"""Non-tenant foundation metadata only. Tenant schema and RLS arrive in Phase 3."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_metadata",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.execute("INSERT INTO platform_metadata (key, value) VALUES ('schema_version', 'phase2')")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'insightrag_runtime') THEN
            GRANT SELECT ON platform_metadata, alembic_version TO insightrag_runtime;
        END IF;
    END $$""")


def downgrade() -> None:
    op.drop_table("platform_metadata")
