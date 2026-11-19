"""Evaluate analytics resource grants once per scoped query, not once per fact row."""

from alembic import op

revision = "0008_analytics_scope"
down_revision = "0007_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY analytics_sales_read ON public.analytics_sales_rows")
    op.execute("""CREATE POLICY analytics_sales_read ON public.analytics_sales_rows
      FOR SELECT TO insightrag_runtime USING (
        org_id = insightrag_security.context_org_id()
        AND resource_id = NULLIF(current_setting('app.analytics_resource_id', true),'')::uuid
        AND (SELECT insightrag_security.can_resource(
          insightrag_security.context_org_id(),
          NULLIF(current_setting('app.analytics_resource_id', true),'')::uuid,'query'))
        AND region IN (SELECT e.region FROM public.row_entitlements e
          WHERE e.org_id=insightrag_security.context_org_id()
            AND e.resource_id=NULLIF(current_setting('app.analytics_resource_id', true),'')::uuid
            AND e.user_id=insightrag_security.context_user_id())
        AND version_id = (SELECT r.active_version FROM public.resources r
          WHERE r.org_id=insightrag_security.context_org_id()
            AND r.id=NULLIF(current_setting('app.analytics_resource_id', true),'')::uuid)
      )""")


def downgrade() -> None:
    op.execute("DROP POLICY analytics_sales_read ON public.analytics_sales_rows")
    op.execute("""CREATE POLICY analytics_sales_read ON public.analytics_sales_rows
      FOR SELECT TO insightrag_runtime USING (
        insightrag_security.can_dataset_row(org_id,resource_id,region) AND EXISTS(
          SELECT 1 FROM public.resources r WHERE r.org_id=analytics_sales_rows.org_id
            AND r.id=analytics_sales_rows.resource_id
            AND r.active_version=analytics_sales_rows.version_id)
      )""")
