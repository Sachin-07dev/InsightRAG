"""Keep versioned blobs pending until trusted cleanup finishes."""
# ruff: noqa: E501

from alembic import op

revision = "0004_ingestion_deletion"
down_revision = "0003_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The Phase 3 deletion function predates versioned objects. Refuse to mark
    # a resource purged while any version still owns a blob.
    op.execute("""CREATE OR REPLACE FUNCTION insightrag_security.purge_deleted_resource(p_job uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
      DECLARE j public.security_jobs%ROWTYPE; r public.resources%ROWTYPE; rev bigint;
      BEGIN
        SELECT policy_revision INTO rev FROM public.orgs
          WHERE id=insightrag_security.context_org_id() FOR SHARE;
        IF NOT FOUND OR NOT insightrag_security.is_member(insightrag_security.context_org_id())
          THEN RETURN 'denied'; END IF;
        SELECT * INTO j FROM public.security_jobs WHERE org_id=insightrag_security.context_org_id()
          AND id=p_job AND requested_by=insightrag_security.context_user_id() FOR UPDATE;
        IF NOT FOUND OR j.action<>'delete' THEN RETURN 'denied'; END IF;
        IF j.policy_revision<>rev OR NOT insightrag_security.can_job_resource(
          j.org_id,j.resource_id,'delete',j.object_key) THEN
          IF j.state IN ('queued','running') THEN UPDATE public.security_jobs SET state='denied'
            WHERE org_id=j.org_id AND id=p_job; END IF;
          RETURN 'denied'; END IF;
        IF j.state='completed' THEN RETURN 'completed'; END IF;
        IF j.state='held' THEN RETURN 'held'; END IF;
        IF j.state NOT IN ('queued','running') THEN RETURN 'denied'; END IF;
        SELECT * INTO r FROM public.resources WHERE org_id=j.org_id AND id=j.resource_id;
        IF NOT FOUND OR r.state<>'deleted' THEN RETURN 'denied'; END IF;
        IF r.legal_hold OR r.retention_until>now() THEN
          UPDATE public.security_jobs SET state='held' WHERE org_id=j.org_id AND id=p_job;
          RETURN 'held'; END IF;
        IF r.object_key IS NOT NULL OR EXISTS (SELECT 1 FROM public.document_versions v
          WHERE v.org_id=j.org_id AND v.resource_id=j.resource_id) THEN
          RETURN 'pending_storage'; END IF;
        DELETE FROM public.document_chunks WHERE org_id=j.org_id AND resource_id=j.resource_id;
        DELETE FROM public.dataset_rows WHERE org_id=j.org_id AND resource_id=j.resource_id;
        UPDATE public.security_jobs SET state='completed' WHERE org_id=j.org_id AND id=p_job;
        RETURN 'completed';
      END $fn$""")
    op.execute("""CREATE FUNCTION insightrag_security.ingestion_deletion_keys(p_job uuid)
      RETURNS text[] LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
      DECLARE j public.security_jobs%ROWTYPE; r public.resources%ROWTYPE; rev bigint; keys text[];
      BEGIN
        SELECT policy_revision INTO rev FROM public.orgs
          WHERE id=insightrag_security.context_org_id() FOR SHARE;
        SELECT * INTO j FROM public.security_jobs WHERE org_id=insightrag_security.context_org_id()
          AND id=p_job AND requested_by=insightrag_security.context_user_id();
        IF NOT FOUND OR j.action<>'delete' OR j.state NOT IN ('queued','running')
          OR j.policy_revision IS DISTINCT FROM rev OR NOT insightrag_security.can_job_resource(
          j.org_id,j.resource_id,'delete',j.object_key) THEN RETURN NULL; END IF;
        SELECT * INTO r FROM public.resources WHERE org_id=j.org_id AND id=j.resource_id;
        IF NOT FOUND OR r.state<>'deleted' OR r.legal_hold OR r.retention_until>now()
          THEN RETURN NULL; END IF;
        SELECT array_agg(v.object_key ORDER BY v.version_number) INTO keys
          FROM public.document_versions v WHERE v.org_id=j.org_id AND v.resource_id=j.resource_id;
        IF r.object_key IS NOT NULL THEN keys:=array_append(COALESCE(keys,ARRAY[]::text[]),r.object_key); END IF;
        RETURN COALESCE(keys,ARRAY[]::text[]);
      END $fn$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.ingestion_deletion_keys(uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.ingestion_deletion_keys(uuid) TO insightrag_runtime"
    )
    op.execute("""CREATE FUNCTION insightrag_security.finish_ingestion_deletion(p_job uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
      DECLARE j public.security_jobs%ROWTYPE; keys text[];
      BEGIN
        keys:=insightrag_security.ingestion_deletion_keys(p_job);
        IF keys IS NULL THEN RETURN 'denied'; END IF;
        SELECT * INTO j FROM public.security_jobs WHERE org_id=insightrag_security.context_org_id()
          AND id=p_job AND requested_by=insightrag_security.context_user_id() FOR UPDATE;
        DELETE FROM public.ingestion_chunks WHERE org_id=j.org_id AND resource_id=j.resource_id;
        DELETE FROM public.ingestion_dataset_rows WHERE org_id=j.org_id AND resource_id=j.resource_id;
        DELETE FROM public.ingestion_jobs WHERE org_id=j.org_id AND resource_id=j.resource_id;
        DELETE FROM public.document_versions WHERE org_id=j.org_id AND resource_id=j.resource_id;
        UPDATE public.resources SET active_version=NULL,latest_version=NULL,object_key=NULL
          WHERE org_id=j.org_id AND id=j.resource_id;
        RETURN insightrag_security.purge_deleted_resource(p_job);
      END $fn$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.finish_ingestion_deletion(uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.finish_ingestion_deletion(uuid) TO insightrag_runtime"
    )
    op.execute("UPDATE public.platform_metadata SET value='phase4' WHERE key='schema_version'")


def downgrade() -> None:
    op.execute("DROP FUNCTION insightrag_security.finish_ingestion_deletion(uuid)")
    op.execute("DROP FUNCTION insightrag_security.ingestion_deletion_keys(uuid)")
    # A downgrade must not restore the old unsafe purge while version rows exist.
    count = (
        op.get_bind().exec_driver_sql("SELECT count(*) FROM public.document_versions").scalar_one()
    )
    if count:
        raise RuntimeError("Cannot downgrade deletion guard with versioned objects present")
