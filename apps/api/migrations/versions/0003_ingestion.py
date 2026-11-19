"""Versioned ingestion catalog, staging RLS and atomic publication."""
# ruff: noqa: E501

from alembic import op

revision = "0003_ingestion"
down_revision = "0002_tenant_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.resources ADD COLUMN active_version uuid, ADD COLUMN latest_version uuid"
    )
    op.execute("""CREATE TABLE public.document_versions (
        org_id uuid NOT NULL, resource_id uuid NOT NULL, id uuid NOT NULL,
        version_number integer NOT NULL, sha256 text NOT NULL, object_key text NOT NULL,
        filename text NOT NULL, media_type text NOT NULL, state text NOT NULL DEFAULT 'queued',
        model_id text, created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (org_id,resource_id,id),
        UNIQUE (org_id,resource_id,version_number),
        FOREIGN KEY (org_id,resource_id) REFERENCES public.resources(org_id,id),
        FOREIGN KEY (org_id,created_by) REFERENCES public.org_memberships(org_id,user_id),
        CHECK (state IN ('queued','processing','published','superseded','failed','cancelled')),
        CHECK (sha256 ~ '^[0-9a-f]{64}$')
    )""")
    op.execute("""CREATE TABLE public.ingestion_jobs (
        org_id uuid NOT NULL, id uuid NOT NULL, resource_id uuid NOT NULL,
        version_id uuid NOT NULL, requested_by uuid NOT NULL, policy_revision bigint NOT NULL,
        state text NOT NULL DEFAULT 'queued', stage text NOT NULL DEFAULT 'queued',
        attempts integer NOT NULL DEFAULT 0, error_code text,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (org_id,id),
        UNIQUE (org_id,resource_id,version_id),
        FOREIGN KEY (org_id,resource_id,version_id) REFERENCES public.document_versions(org_id,resource_id,id),
        FOREIGN KEY (org_id,requested_by) REFERENCES public.org_memberships(org_id,user_id),
        CHECK (state IN ('queued','running','completed','failed','cancelled')),
        CHECK (stage IN ('queued','parsing','embedding','indexing','published','failed','cancelled')),
        CHECK (attempts BETWEEN 0 AND 10)
    )""")
    op.execute("""CREATE TABLE public.ingestion_chunks (
        org_id uuid NOT NULL, resource_id uuid NOT NULL, version_id uuid NOT NULL,
        position integer NOT NULL, text text NOT NULL, locator text NOT NULL,
        heading text, token_count integer NOT NULL, embedding vector(1536),
        PRIMARY KEY (org_id,resource_id,version_id,position),
        FOREIGN KEY (org_id,resource_id,version_id) REFERENCES public.document_versions(org_id,resource_id,id),
        CHECK (position >= 0 AND token_count > 0 AND length(text) > 0)
    )""")
    op.execute("""CREATE TABLE public.ingestion_dataset_rows (
        org_id uuid NOT NULL, resource_id uuid NOT NULL, version_id uuid NOT NULL,
        row_number integer NOT NULL, region text NOT NULL, payload jsonb NOT NULL,
        PRIMARY KEY (org_id,resource_id,version_id,row_number),
        FOREIGN KEY (org_id,resource_id,version_id) REFERENCES public.document_versions(org_id,resource_id,id),
        CHECK (row_number >= 2 AND length(region) BETWEEN 1 AND 128)
    )""")
    op.execute(
        "CREATE INDEX ingestion_chunks_hnsw ON public.ingestion_chunks USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ingestion_jobs_reconcile ON public.ingestion_jobs (state,updated_at) WHERE state IN ('queued','running')"
    )
    for table in (
        "document_versions",
        "ingestion_jobs",
        "ingestion_chunks",
        "ingestion_dataset_rows",
    ):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(
        "GRANT SELECT ON public.document_versions,public.ingestion_jobs,public.ingestion_chunks,public.ingestion_dataset_rows TO insightrag_policy_reader"
    )
    op.execute(
        "GRANT SELECT ON public.document_versions,public.ingestion_jobs,public.ingestion_chunks,public.ingestion_dataset_rows TO insightrag_runtime"
    )
    op.execute(
        "GRANT INSERT ON public.ingestion_chunks,public.ingestion_dataset_rows TO insightrag_runtime"
    )
    op.execute(
        "GRANT UPDATE (state,stage,attempts,error_code,updated_at) ON public.ingestion_jobs TO insightrag_runtime"
    )
    op.execute("""CREATE POLICY version_read ON public.document_versions FOR SELECT TO insightrag_runtime
      USING (insightrag_security.can_resource_metadata(org_id,resource_id))""")
    op.execute("""CREATE POLICY job_read ON public.ingestion_jobs FOR SELECT TO insightrag_runtime
      USING (insightrag_security.is_member(org_id) AND requested_by=insightrag_security.context_user_id())""")
    op.execute("""CREATE POLICY job_update ON public.ingestion_jobs FOR UPDATE TO insightrag_runtime
      USING (insightrag_security.is_member(org_id) AND requested_by=insightrag_security.context_user_id()
             AND insightrag_security.can_resource(org_id,resource_id,'upload'))
      WITH CHECK (insightrag_security.is_member(org_id) AND requested_by=insightrag_security.context_user_id()
                  AND insightrag_security.can_resource(org_id,resource_id,'upload'))""")
    op.execute("""CREATE POLICY chunk_read ON public.ingestion_chunks FOR SELECT TO insightrag_runtime
      USING (insightrag_security.can_resource(org_id,resource_id,'read') AND EXISTS (
        SELECT 1 FROM public.resources r WHERE r.org_id=ingestion_chunks.org_id
        AND r.id=ingestion_chunks.resource_id AND r.active_version=ingestion_chunks.version_id))""")
    op.execute("""CREATE POLICY chunk_stage ON public.ingestion_chunks FOR INSERT TO insightrag_runtime
      WITH CHECK (insightrag_security.can_resource(org_id,resource_id,'upload') AND EXISTS (
        SELECT 1 FROM public.ingestion_jobs j WHERE j.org_id=ingestion_chunks.org_id
        AND j.resource_id=ingestion_chunks.resource_id AND j.version_id=ingestion_chunks.version_id
        AND j.requested_by=insightrag_security.context_user_id() AND j.state='running'
        AND j.policy_revision=(SELECT o.policy_revision FROM public.orgs o WHERE o.id=j.org_id)))""")
    op.execute("""CREATE POLICY dataset_read ON public.ingestion_dataset_rows FOR SELECT TO insightrag_runtime
      USING (insightrag_security.can_dataset_row(org_id,resource_id,region) AND EXISTS (
        SELECT 1 FROM public.resources r WHERE r.org_id=ingestion_dataset_rows.org_id
        AND r.id=ingestion_dataset_rows.resource_id AND r.active_version=ingestion_dataset_rows.version_id))""")
    op.execute("""CREATE POLICY dataset_stage ON public.ingestion_dataset_rows FOR INSERT TO insightrag_runtime
      WITH CHECK (insightrag_security.can_resource(org_id,resource_id,'upload') AND EXISTS (
        SELECT 1 FROM public.ingestion_jobs j WHERE j.org_id=ingestion_dataset_rows.org_id
        AND j.resource_id=ingestion_dataset_rows.resource_id AND j.version_id=ingestion_dataset_rows.version_id
        AND j.requested_by=insightrag_security.context_user_id() AND j.state='running'
        AND j.policy_revision=(SELECT o.policy_revision FROM public.orgs o WHERE o.id=j.org_id)))""")
    op.execute("""CREATE FUNCTION insightrag_security.reserve_ingestion(
        p_org uuid,p_resource uuid,p_version uuid,p_job uuid,p_hash text,p_key text,
        p_filename text,p_media text) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog AS $fn$
      DECLARE r public.resources%ROWTYPE; n integer; previous uuid; rev bigint;
      BEGIN
        IF p_org IS DISTINCT FROM insightrag_security.context_org_id()
          OR p_hash !~ '^[0-9a-f]{64}$' OR length(p_key)>512
          OR p_key IS DISTINCT FROM 'organizations/'||p_org||'/workspaces/'||(
            SELECT workspace_id FROM public.resources WHERE org_id=p_org AND id=p_resource
          )||'/resources/'||p_resource||'/versions/'||p_version||'/source'
          OR length(p_filename)>128 OR length(p_media)>128 THEN RETURN 'denied'; END IF;
        SELECT * INTO r FROM public.resources WHERE org_id=p_org AND id=p_resource FOR UPDATE;
        IF NOT FOUND OR r.state='deleted' OR NOT insightrag_security.can_resource(p_org,p_resource,'upload')
          THEN RETURN 'denied'; END IF;
        IF r.latest_version IS NOT NULL THEN
          SELECT id INTO previous FROM public.document_versions WHERE org_id=p_org AND resource_id=p_resource
            AND id=r.latest_version AND sha256=p_hash AND state IN ('queued','processing','published');
          IF previous IS NOT NULL THEN RETURN 'duplicate:'||previous::text; END IF;
        END IF;
        SELECT COALESCE(max(version_number),0)+1 INTO n FROM public.document_versions
          WHERE org_id=p_org AND resource_id=p_resource;
        SELECT policy_revision INTO rev FROM public.orgs WHERE id=p_org;
        INSERT INTO public.document_versions(org_id,resource_id,id,version_number,sha256,object_key,
          filename,media_type,created_by) VALUES(p_org,p_resource,p_version,n,p_hash,p_key,
          p_filename,p_media,insightrag_security.context_user_id());
        INSERT INTO public.ingestion_jobs(org_id,id,resource_id,version_id,requested_by,policy_revision)
          VALUES(p_org,p_job,p_resource,p_version,insightrag_security.context_user_id(),rev);
        UPDATE public.resources SET latest_version=p_version WHERE org_id=p_org AND id=p_resource;
        RETURN 'created';
      END $fn$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.reserve_ingestion(uuid,uuid,uuid,uuid,text,text,text,text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.reserve_ingestion(uuid,uuid,uuid,uuid,text,text,text,text) TO insightrag_runtime"
    )
    op.execute("""CREATE FUNCTION insightrag_security.publish_ingestion(p_org uuid,p_job uuid,p_model text) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
      DECLARE j public.ingestion_jobs%ROWTYPE; r public.resources%ROWTYPE; old uuid;
      BEGIN
        IF p_org IS DISTINCT FROM insightrag_security.context_org_id() THEN RETURN 'denied'; END IF;
        SELECT * INTO j FROM public.ingestion_jobs WHERE org_id=p_org AND id=p_job FOR UPDATE;
        IF NOT FOUND OR j.requested_by IS DISTINCT FROM insightrag_security.context_user_id()
          OR j.state NOT IN ('running','completed') THEN RETURN 'denied'; END IF;
        IF j.state='completed' THEN RETURN 'completed'; END IF;
        SELECT * INTO r FROM public.resources WHERE org_id=p_org AND id=j.resource_id FOR UPDATE;
        IF NOT FOUND OR r.state='deleted' OR r.latest_version IS DISTINCT FROM j.version_id
          OR j.policy_revision IS DISTINCT FROM (SELECT policy_revision FROM public.orgs WHERE id=p_org)
          OR NOT insightrag_security.can_resource(p_org,j.resource_id,'upload') THEN RETURN 'stale'; END IF;
        IF r.kind='document' AND (NOT EXISTS (SELECT 1 FROM public.ingestion_chunks c WHERE
          c.org_id=p_org AND c.resource_id=j.resource_id AND c.version_id=j.version_id
          AND c.embedding IS NOT NULL) OR EXISTS (SELECT 1 FROM public.ingestion_chunks c WHERE
          c.org_id=p_org AND c.resource_id=j.resource_id AND c.version_id=j.version_id
          AND c.embedding IS NULL)) THEN RETURN 'incomplete'; END IF;
        IF r.kind='dataset' AND NOT EXISTS (SELECT 1 FROM public.ingestion_dataset_rows d WHERE
          d.org_id=p_org AND d.resource_id=j.resource_id AND d.version_id=j.version_id)
          THEN RETURN 'incomplete'; END IF;
        old:=r.active_version;
        IF old IS NOT NULL THEN UPDATE public.document_versions SET state='superseded' WHERE
          org_id=p_org AND resource_id=j.resource_id AND id=old; END IF;
        UPDATE public.document_versions SET state='published',model_id=p_model WHERE
          org_id=p_org AND resource_id=j.resource_id AND id=j.version_id;
        UPDATE public.resources SET active_version=j.version_id,state='active' WHERE
          org_id=p_org AND id=j.resource_id;
        UPDATE public.ingestion_jobs SET state='completed',stage='published',updated_at=now()
          WHERE org_id=p_org AND id=p_job;
        RETURN 'published';
      END $fn$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.publish_ingestion(uuid,uuid,text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.publish_ingestion(uuid,uuid,text) TO insightrag_runtime"
    )
    op.execute("UPDATE public.platform_metadata SET value='phase4' WHERE key='schema_version'")


def downgrade() -> None:
    op.execute("DROP FUNCTION insightrag_security.publish_ingestion(uuid,uuid,text)")
    op.execute(
        "DROP FUNCTION insightrag_security.reserve_ingestion(uuid,uuid,uuid,uuid,text,text,text,text)"
    )
    for table in (
        "ingestion_dataset_rows",
        "ingestion_chunks",
        "ingestion_jobs",
        "document_versions",
    ):
        op.execute(f"DROP TABLE public.{table}")
    op.execute("ALTER TABLE public.resources DROP COLUMN active_version,DROP COLUMN latest_version")
    op.execute("UPDATE public.platform_metadata SET value='phase3' WHERE key='schema_version'")
