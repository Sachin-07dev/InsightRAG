"""Explicit reindex can create a new version for unchanged source bytes."""
# ruff: noqa: E501

from alembic import op

revision = "0005_reindex"
down_revision = "0004_ingestion_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE FUNCTION insightrag_security.reserve_ingestion_force(
      p_org uuid,p_resource uuid,p_version uuid,p_job uuid,p_hash text,p_key text,
      p_filename text,p_media text) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
      SET search_path=pg_catalog AS $fn$
      DECLARE result text; r public.resources%ROWTYPE; n integer; rev bigint;
      BEGIN
        result:=insightrag_security.reserve_ingestion(p_org,p_resource,p_version,p_job,
          p_hash,p_key,p_filename,p_media);
        IF result IN ('created','denied') THEN RETURN result; END IF;
        IF result NOT LIKE 'duplicate:%' THEN RETURN 'denied'; END IF;
        -- The ordinary reservation already validated key grammar and locked the
        -- resource; only its duplicate shortcut prevented a new model profile.
        SELECT * INTO r FROM public.resources WHERE org_id=p_org AND id=p_resource FOR UPDATE;
        IF NOT FOUND OR r.state='deleted' OR r.latest_version IS NULL
          OR NOT insightrag_security.can_resource(p_org,p_resource,'upload') THEN
          RETURN 'denied'; END IF;
        SELECT COALESCE(max(version_number),0)+1 INTO n FROM public.document_versions
          WHERE org_id=p_org AND resource_id=p_resource;
        SELECT policy_revision INTO rev FROM public.orgs WHERE id=p_org;
        INSERT INTO public.document_versions(org_id,resource_id,id,version_number,sha256,
          object_key,filename,media_type,created_by)
          VALUES(p_org,p_resource,p_version,n,p_hash,p_key,p_filename,p_media,
          insightrag_security.context_user_id());
        INSERT INTO public.ingestion_jobs(org_id,id,resource_id,version_id,requested_by,policy_revision)
          VALUES(p_org,p_job,p_resource,p_version,insightrag_security.context_user_id(),rev);
        UPDATE public.resources SET latest_version=p_version WHERE org_id=p_org AND id=p_resource;
        RETURN 'created';
      END $fn$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.reserve_ingestion_force(uuid,uuid,uuid,uuid,text,text,text,text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.reserve_ingestion_force(uuid,uuid,uuid,uuid,text,text,text,text) TO insightrag_runtime"
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION insightrag_security.reserve_ingestion_force(uuid,uuid,uuid,uuid,text,text,text,text)"
    )
