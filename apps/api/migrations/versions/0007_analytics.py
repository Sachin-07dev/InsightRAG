"""Typed governed sales projection and row-level analytics isolation."""
# ruff: noqa: E501

from alembic import op

revision = "0007_analytics"
down_revision = "0006_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.orgs ADD COLUMN reporting_timezone text NOT NULL DEFAULT 'UTC'")
    op.execute("""CREATE TABLE public.analytics_sales_rows (
      org_id uuid NOT NULL, resource_id uuid NOT NULL, version_id uuid NOT NULL,
      row_number integer NOT NULL, transaction_id text NOT NULL, transaction_date date NOT NULL,
      region text NOT NULL, product text NOT NULL, revenue numeric(20,4) NOT NULL,
      cost numeric(20,4) NOT NULL, units integer NOT NULL, returned_units integer NOT NULL,
      currency char(3) NOT NULL,
      PRIMARY KEY(org_id,resource_id,version_id,row_number),
      UNIQUE(org_id,resource_id,version_id,transaction_id),
      FOREIGN KEY(org_id,resource_id,version_id)
        REFERENCES public.document_versions(org_id,resource_id,id) ON DELETE CASCADE,
      CHECK(row_number>=2 AND length(region) BETWEEN 1 AND 128 AND length(product) BETWEEN 1 AND 128),
      CHECK(units>=0 AND returned_units>=0 AND length(transaction_id) BETWEEN 1 AND 128),
      CHECK(currency ~ '^[A-Z]{3}$')
    )""")
    op.execute("CREATE INDEX analytics_sales_scope_date ON public.analytics_sales_rows(org_id,resource_id,version_id,currency,transaction_date,region)")
    op.execute("ALTER TABLE public.analytics_sales_rows ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.analytics_sales_rows FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.analytics_sales_rows FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT ON public.analytics_sales_rows TO insightrag_runtime")
    op.execute("""CREATE POLICY analytics_sales_read ON public.analytics_sales_rows FOR SELECT TO insightrag_runtime
      USING(insightrag_security.can_dataset_row(org_id,resource_id,region) AND EXISTS(
        SELECT 1 FROM public.resources r WHERE r.org_id=analytics_sales_rows.org_id
        AND r.id=analytics_sales_rows.resource_id AND r.active_version=analytics_sales_rows.version_id))""")
    op.execute("""CREATE POLICY analytics_sales_stage ON public.analytics_sales_rows FOR INSERT TO insightrag_runtime
      WITH CHECK(insightrag_security.can_resource(org_id,resource_id,'upload') AND EXISTS(
        SELECT 1 FROM public.ingestion_jobs j WHERE j.org_id=analytics_sales_rows.org_id
        AND j.resource_id=analytics_sales_rows.resource_id AND j.version_id=analytics_sales_rows.version_id
        AND j.requested_by=insightrag_security.context_user_id() AND j.state='running'
        AND j.policy_revision=(SELECT o.policy_revision FROM public.orgs o WHERE o.id=j.org_id)))""")
    op.execute("""CREATE FUNCTION insightrag_security.has_complete_sales_scope(p_org uuid,p_resource uuid)
      RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
      SELECT insightrag_security.can_resource(p_org,p_resource,'query')
        AND EXISTS(SELECT 1 FROM public.analytics_sales_rows a JOIN public.resources r
          ON r.org_id=a.org_id AND r.id=a.resource_id AND r.active_version=a.version_id
          WHERE a.org_id=p_org AND a.resource_id=p_resource)
        AND NOT EXISTS(SELECT 1 FROM public.analytics_sales_rows a JOIN public.resources r
          ON r.org_id=a.org_id AND r.id=a.resource_id AND r.active_version=a.version_id
          WHERE a.org_id=p_org AND a.resource_id=p_resource AND NOT EXISTS(
            SELECT 1 FROM public.row_entitlements e WHERE e.org_id=a.org_id
              AND e.resource_id=a.resource_id AND e.user_id=insightrag_security.context_user_id()
              AND e.region=a.region))
      $fn$""")
    op.execute("REVOKE ALL ON FUNCTION insightrag_security.has_complete_sales_scope(uuid,uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION insightrag_security.has_complete_sales_scope(uuid,uuid) TO insightrag_runtime")
    op.execute("UPDATE public.platform_metadata SET value='phase6' WHERE key='schema_version'")


def downgrade() -> None:
    op.execute("DROP FUNCTION insightrag_security.has_complete_sales_scope(uuid,uuid)")
    op.execute("DROP TABLE public.analytics_sales_rows")
    op.execute("ALTER TABLE public.orgs DROP COLUMN reporting_timezone")
    op.execute("UPDATE public.platform_metadata SET value='phase5' WHERE key='schema_version'")
