"""Frozen tenant-security schema, scoped RLS helpers and least-privilege grants."""
# ruff: noqa: E501

from alembic import op

revision = "0002_tenant_security"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

LOCK_MEMBER_REVISION_SQL = """CREATE FUNCTION insightrag_security.lock_member_policy_revision(p_org uuid) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $function$
    DECLARE v_revision bigint;
    BEGIN
      IF NOT insightrag_security.is_member(p_org) THEN RETURN NULL; END IF;
      SELECT o.policy_revision INTO v_revision FROM public.orgs AS o WHERE o.id = p_org FOR SHARE;
      IF NOT insightrag_security.is_member(p_org) THEN RETURN NULL; END IF;
      RETURN v_revision;
    END $function$"""

# This SQL snapshot is deliberately independent of mutable application metadata.
DDL_STATEMENTS = (
    """
CREATE TABLE orgs (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	name TEXT NOT NULL, 
	home_region TEXT NOT NULL, 
	retention_days INTEGER DEFAULT '30' NOT NULL, 
	policy_revision BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (retention_days >= 0 AND policy_revision >= 1)
)

""",
    """
CREATE TABLE security_users (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	issuer TEXT NOT NULL, 
	subject TEXT NOT NULL, 
	clearance INTEGER DEFAULT '0' NOT NULL, 
	active BOOLEAN DEFAULT true NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (issuer, subject), 
	CHECK (clearance BETWEEN 0 AND 3)
)

""",
    """
CREATE TABLE groups (
	org_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	name TEXT NOT NULL, 
	PRIMARY KEY (org_id, id), 
	FOREIGN KEY(org_id) REFERENCES orgs (id)
)

""",
    """
CREATE TABLE org_memberships (
	org_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	role TEXT NOT NULL, 
	status TEXT DEFAULT 'active' NOT NULL, 
	revision BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (org_id, user_id), 
	FOREIGN KEY(org_id) REFERENCES orgs (id), 
	CHECK (role IN ('owner','admin','steward','analyst','viewer','auditor')), 
	CHECK (status IN ('active','suspended') AND revision >= 1), 
	FOREIGN KEY(user_id) REFERENCES security_users (id)
)

""",
    """
CREATE TABLE workspaces (
	org_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	name TEXT NOT NULL, 
	PRIMARY KEY (org_id, id), 
	FOREIGN KEY(org_id) REFERENCES orgs (id)
)

""",
    """
CREATE TABLE group_memberships (
	org_id UUID NOT NULL, 
	group_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	PRIMARY KEY (org_id, group_id, user_id), 
	FOREIGN KEY(org_id, group_id) REFERENCES groups (org_id, id), 
	FOREIGN KEY(org_id, user_id) REFERENCES org_memberships (org_id, user_id)
)

""",
    """
CREATE TABLE resources (
	org_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	workspace_id UUID NOT NULL, 
	kind TEXT NOT NULL, 
	title TEXT NOT NULL, 
	classification INTEGER DEFAULT '0' NOT NULL, 
	require_mfa BOOLEAN DEFAULT false NOT NULL, 
	state TEXT DEFAULT 'quarantine' NOT NULL, 
	purpose TEXT, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	legal_hold BOOLEAN DEFAULT false NOT NULL, 
	retention_until TIMESTAMP WITH TIME ZONE, 
	object_key TEXT, 
	created_by UUID DEFAULT NULLIF(current_setting('app.user_id', true), '')::uuid NOT NULL, 
	created_in_transaction TEXT DEFAULT pg_current_xact_id()::text NOT NULL, 
	PRIMARY KEY (org_id, id), 
	FOREIGN KEY(org_id, workspace_id) REFERENCES workspaces (org_id, id), 
	FOREIGN KEY(org_id, created_by) REFERENCES org_memberships (org_id, user_id), 
	CHECK (kind IN ('document','dataset')), 
	CHECK (classification BETWEEN 0 AND 3), 
	CHECK (state IN ('quarantine','active','deleted')), 
	CHECK ((state = 'deleted') = (deleted_at IS NOT NULL))
)

""",
    """
CREATE TABLE workspace_memberships (
	org_id UUID NOT NULL, 
	workspace_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	role TEXT NOT NULL, 
	PRIMARY KEY (org_id, workspace_id, user_id), 
	FOREIGN KEY(org_id, workspace_id) REFERENCES workspaces (org_id, id), 
	FOREIGN KEY(org_id, user_id) REFERENCES org_memberships (org_id, user_id), 
	CHECK (role IN ('manager','steward','analyst','viewer'))
)

""",
    """
CREATE TABLE audit_events (
	org_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	actor_id UUID NOT NULL, 
	action TEXT NOT NULL, 
	resource_id UUID, 
	outcome TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	request_id TEXT NOT NULL, 
	PRIMARY KEY (org_id, id), 
	FOREIGN KEY(org_id, actor_id) REFERENCES org_memberships (org_id, user_id), 
	FOREIGN KEY(org_id, resource_id) REFERENCES resources (org_id, id)
)

""",
    """
CREATE TABLE dataset_rows (
	org_id UUID NOT NULL, 
	resource_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	region TEXT NOT NULL, 
	payload JSONB NOT NULL, 
	PRIMARY KEY (org_id, resource_id, id), 
	FOREIGN KEY(org_id, resource_id) REFERENCES resources (org_id, id)
)

""",
    """
CREATE TABLE document_chunks (
	org_id UUID NOT NULL, 
	resource_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	text TEXT NOT NULL, 
	embedding vector(3), 
	PRIMARY KEY (org_id, resource_id, id), 
	FOREIGN KEY(org_id, resource_id) REFERENCES resources (org_id, id)
)

""",
    """
CREATE TABLE resource_grants (
	org_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	resource_id UUID NOT NULL, 
	user_id UUID, 
	group_id UUID, 
	action TEXT NOT NULL, 
	PRIMARY KEY (org_id, id), 
	FOREIGN KEY(org_id, resource_id) REFERENCES resources (org_id, id), 
	FOREIGN KEY(org_id, user_id) REFERENCES org_memberships (org_id, user_id), 
	FOREIGN KEY(org_id, group_id) REFERENCES groups (org_id, id), 
	CHECK ((user_id IS NULL) <> (group_id IS NULL)), 
	CHECK (action IN ('read','query','upload','delete','manage')), 
	UNIQUE (org_id, resource_id, user_id, action), 
	UNIQUE (org_id, resource_id, group_id, action)
)

""",
    """
CREATE TABLE row_entitlements (
	org_id UUID NOT NULL, 
	resource_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	region TEXT NOT NULL, 
	PRIMARY KEY (org_id, resource_id, user_id, region), 
	FOREIGN KEY(org_id, resource_id) REFERENCES resources (org_id, id), 
	FOREIGN KEY(org_id, user_id) REFERENCES org_memberships (org_id, user_id)
)

""",
    """
CREATE TABLE security_jobs (
	org_id UUID NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	resource_id UUID NOT NULL, 
	requested_by UUID NOT NULL, 
	action TEXT NOT NULL, 
	state TEXT DEFAULT 'queued' NOT NULL, 
	policy_revision BIGINT NOT NULL, 
	object_key TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (org_id, id), 
	FOREIGN KEY(org_id, resource_id) REFERENCES resources (org_id, id), 
	FOREIGN KEY(org_id, requested_by) REFERENCES org_memberships (org_id, user_id), 
	CHECK (action IN ('read','query','upload','delete','manage')), 
	CHECK (state IN ('queued','running','denied','completed','held','failed')), 
	CHECK (policy_revision >= 1)
)

""",
    """CREATE INDEX ix_group_user ON group_memberships (org_id, user_id)""",
    """CREATE INDEX ix_resource_workspace ON resources (org_id, workspace_id)""",
    """CREATE INDEX ix_grant_resource ON resource_grants (org_id, resource_id)""",
)

# (name, declaration arguments, identity arguments, return type, fixed SQL body).
# Every catalog read is fully qualified; the definer owns no application tables.
FUNCTIONS = (
    (
        "context_user_id",
        "",
        "",
        "uuid",
        "SELECT NULLIF(current_setting('app.user_id', true), '')::uuid",
    ),
    (
        "context_org_id",
        "",
        "",
        "uuid",
        "SELECT NULLIF(current_setting('app.organization_id', true), '')::uuid",
    ),
    (
        "context_mfa",
        "",
        "",
        "boolean",
        "SELECT COALESCE(current_setting('app.mfa', true), 'false') = 'true'",
    ),
    (
        "security_identity",
        "p_issuer text, p_subject text",
        "text, text",
        "TABLE(id uuid, clearance integer)",
        """
        SELECT u.id, u.clearance FROM public.security_users AS u
        WHERE u.issuer = p_issuer AND u.subject = p_subject AND u.active
    """,
    ),
    (
        "org_role",
        "p_org uuid",
        "uuid",
        "text",
        """
        SELECT m.role FROM public.org_memberships AS m
        JOIN public.security_users AS u ON u.id = m.user_id AND u.active
        WHERE p_org = insightrag_security.context_org_id()
          AND m.org_id = p_org AND m.user_id = insightrag_security.context_user_id()
          AND m.status = 'active'
    """,
    ),
    (
        "is_member",
        "p_org uuid",
        "uuid",
        "boolean",
        """
        SELECT insightrag_security.org_role(p_org) IS NOT NULL
    """,
    ),
    (
        "user_clearance",
        "",
        "",
        "integer",
        """
        SELECT u.clearance FROM public.security_users AS u
        WHERE u.id = insightrag_security.context_user_id() AND u.active
    """,
    ),
    (
        "has_workspace_capability",
        "p_org uuid, p_workspace uuid, p_action text",
        "uuid, uuid, text",
        "boolean",
        """
        SELECT EXISTS (
            SELECT 1 FROM public.workspace_memberships AS w
            WHERE w.org_id = p_org AND w.workspace_id = p_workspace
              AND w.user_id = insightrag_security.context_user_id()
              AND CASE
                WHEN p_action = 'read' THEN
                  insightrag_security.org_role(p_org) IN ('owner','admin','steward','analyst','viewer')
                  AND w.role IN ('manager','steward','analyst','viewer')
                WHEN p_action = 'query' THEN
                  insightrag_security.org_role(p_org) IN ('owner','admin','steward','analyst')
                  AND w.role IN ('manager','steward','analyst')
                WHEN p_action IN ('upload','delete','manage') THEN
                  insightrag_security.org_role(p_org) IN ('owner','admin','steward')
                  AND w.role IN ('manager','steward')
                ELSE false
              END
        )
    """,
    ),
    (
        "has_resource_grant",
        "p_org uuid, p_resource uuid, p_action text",
        "uuid, uuid, text",
        "boolean",
        """
        SELECT EXISTS (
            SELECT 1 FROM public.resource_grants AS g
            WHERE g.org_id = p_org AND g.resource_id = p_resource AND g.action = p_action
              AND (g.user_id = insightrag_security.context_user_id() OR EXISTS (
                SELECT 1 FROM public.group_memberships AS gm
                WHERE gm.org_id = p_org AND gm.group_id = g.group_id
                  AND gm.user_id = insightrag_security.context_user_id()
              ))
        )
    """,
    ),
    (
        "resource_access",
        "p_org uuid, p_resource uuid, p_action text, p_allow_deleted boolean",
        "uuid, uuid, text, boolean",
        "boolean",
        """
        SELECT EXISTS (
            SELECT 1 FROM public.resources AS r
            WHERE r.org_id = p_org AND r.id = p_resource
              AND insightrag_security.has_workspace_capability(p_org, r.workspace_id, p_action)
              AND insightrag_security.has_resource_grant(p_org, p_resource, p_action)
              AND r.classification <= insightrag_security.user_clearance()
              AND (NOT r.require_mfa OR insightrag_security.context_mfa())
              AND (r.purpose IS NULL OR r.purpose = NULLIF(current_setting('app.purpose', true), ''))
              AND ((p_action IN ('read','query') AND r.state = 'active')
                OR (p_action IN ('upload','delete','manage') AND r.state IN ('active','quarantine'))
                OR (p_allow_deleted AND p_action = 'delete' AND r.state = 'deleted'))
        )
    """,
    ),
    (
        "can_resource",
        "p_org uuid, p_resource uuid, p_action text",
        "uuid, uuid, text",
        "boolean",
        """
        SELECT insightrag_security.resource_access(p_org, p_resource, p_action, false)
    """,
    ),
    (
        "can_resource",
        "p_resource uuid, p_action text",
        "uuid, text",
        "boolean",
        """
        SELECT insightrag_security.can_resource(insightrag_security.context_org_id(), p_resource, p_action)
    """,
    ),
    (
        "can_resource_metadata",
        "p_org uuid, p_resource uuid",
        "uuid, uuid",
        "boolean",
        """
        SELECT insightrag_security.can_resource(p_org, p_resource, 'read')
            OR insightrag_security.can_resource(p_org, p_resource, 'query')
            OR insightrag_security.can_resource(p_org, p_resource, 'upload')
            OR insightrag_security.can_resource(p_org, p_resource, 'delete')
            OR insightrag_security.can_resource(p_org, p_resource, 'manage')
    """,
    ),
    (
        "can_job_resource",
        "p_org uuid, p_resource uuid, p_action text, p_key text",
        "uuid, uuid, text, text",
        "boolean",
        """
        SELECT insightrag_security.resource_access(p_org,p_resource,p_action,true) AND EXISTS (
            SELECT 1 FROM public.resources r WHERE r.org_id=p_org AND r.id=p_resource
              AND (p_key IS NULL OR p_key = r.object_key)
        )
    """,
    ),
    (
        "can_grant_to_member",
        "p_org uuid, p_resource uuid, p_user uuid",
        "uuid, uuid, uuid",
        "boolean",
        """
        SELECT insightrag_security.can_resource(p_org,p_resource,'manage') AND EXISTS (
            SELECT 1 FROM public.org_memberships AS m
            JOIN public.security_users AS u ON u.id = m.user_id AND u.active
            WHERE m.org_id = p_org AND m.user_id = p_user AND m.status = 'active'
        )
    """,
    ),
    (
        "can_manage_grant",
        "p_org uuid, p_resource uuid, p_user uuid, p_group uuid, p_action text",
        "uuid, uuid, uuid, uuid, text",
        "boolean",
        """
        SELECT insightrag_security.can_resource(p_org, p_resource, 'manage') OR EXISTS (
            SELECT 1 FROM public.resources AS r
            WHERE r.org_id = p_org AND r.id = p_resource AND r.state = 'quarantine'
              AND r.created_by = insightrag_security.context_user_id()
              AND r.created_in_transaction = pg_current_xact_id()::text
              AND p_user = insightrag_security.context_user_id() AND p_group IS NULL
              AND p_action IN ('read','query','upload','delete','manage')
              AND insightrag_security.has_workspace_capability(p_org, r.workspace_id, 'upload')
        )
    """,
    ),
    (
        "can_dataset_row",
        "p_org uuid, p_resource uuid, p_region text",
        "uuid, uuid, text",
        "boolean",
        """
        SELECT insightrag_security.can_resource(p_org, p_resource, 'query') AND EXISTS (
            SELECT 1 FROM public.row_entitlements AS e
            WHERE e.org_id = p_org AND e.resource_id = p_resource
              AND e.user_id = insightrag_security.context_user_id() AND e.region = p_region
        )
    """,
    ),
    (
        "can_audit",
        "p_org uuid",
        "uuid",
        "boolean",
        """
        SELECT insightrag_security.org_role(p_org) IN ('owner','admin','auditor')
    """,
    ),
    (
        "can_increment_revision",
        "p_org uuid",
        "uuid",
        "boolean",
        """
        SELECT insightrag_security.org_role(p_org) IN ('owner','admin','steward')
    """,
    ),
)

TENANT_TABLES = (
    "orgs",
    "org_memberships",
    "workspaces",
    "workspace_memberships",
    "groups",
    "group_memberships",
    "resources",
    "resource_grants",
    "dataset_rows",
    "row_entitlements",
    "document_chunks",
    "audit_events",
    "security_jobs",
)


def _policy(
    table: str, name: str, command: str, using: str | None = None, check: str | None = None
) -> None:
    sql = f"CREATE POLICY {name} ON public.{table} FOR {command} TO insightrag_runtime"
    if using is not None:
        sql += f" USING ({using})"
    if check is not None:
        sql += f" WITH CHECK ({check})"
    op.execute(sql)


def upgrade() -> None:
    op.execute("SET LOCAL search_path = public, pg_catalog")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for statement in DDL_STATEMENTS:
        op.execute(statement)
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'insightrag_runtime') THEN
            RAISE EXCEPTION 'Provision the restricted runtime role before tenant migration';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'insightrag_policy_reader') THEN
            CREATE ROLE insightrag_policy_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION BYPASSRLS;
        ELSIF EXISTS (SELECT FROM pg_roles WHERE rolname = 'insightrag_policy_reader' AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolinherit OR NOT rolbypassrls)) THEN
            RAISE EXCEPTION 'Policy reader role has unsafe attributes';
        END IF;
    END $$""")
    op.execute("CREATE SCHEMA insightrag_security")
    op.execute("REVOKE ALL ON SCHEMA insightrag_security FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public, insightrag_security TO insightrag_policy_reader")
    op.execute("GRANT USAGE ON SCHEMA insightrag_security TO insightrag_runtime")
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    policy_catalog = (
        "security_users",
        "orgs",
        "org_memberships",
        "workspaces",
        "workspace_memberships",
        "groups",
        "group_memberships",
        "resources",
        "resource_grants",
        "row_entitlements",
    )
    op.execute(
        "GRANT SELECT ON "
        + ", ".join(f"public.{name}" for name in policy_catalog)
        + " TO insightrag_policy_reader"
    )
    for name, arguments, identity, returns, body in FUNCTIONS:
        qualified = f"insightrag_security.{name}"
        op.execute(
            f"CREATE FUNCTION {qualified}({arguments}) RETURNS {returns} LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $function${body}$function$"
        )
        op.execute(f"ALTER FUNCTION {qualified}({identity}) OWNER TO insightrag_policy_reader")
        op.execute(f"REVOKE ALL ON FUNCTION {qualified}({identity}) FROM PUBLIC")
        # Internal grant/lifecycle helpers are not a public policy-query API.
        if name not in {"resource_access", "has_resource_grant"}:
            op.execute(f"GRANT EXECUTE ON FUNCTION {qualified}({identity}) TO insightrag_runtime")

    for table in (*TENANT_TABLES, "security_users"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC, insightrag_runtime")
    op.execute(
        "GRANT SELECT ON public.security_users, public.orgs, public.org_memberships, public.workspaces, public.workspace_memberships, public.groups, public.group_memberships, public.resources, public.resource_grants, public.dataset_rows, public.row_entitlements, public.document_chunks, public.audit_events, public.security_jobs TO insightrag_runtime"
    )
    op.execute(
        "GRANT INSERT (org_id,id,workspace_id,kind,title,classification,require_mfa,state,purpose) ON public.resources TO insightrag_runtime"
    )
    op.execute("GRANT UPDATE (title,state,deleted_at) ON public.resources TO insightrag_runtime")
    op.execute("GRANT INSERT, DELETE ON public.resource_grants TO insightrag_runtime")
    op.execute("GRANT INSERT ON public.audit_events, public.security_jobs TO insightrag_runtime")
    op.execute("GRANT UPDATE (state) ON public.security_jobs TO insightrag_runtime")
    op.execute("GRANT UPDATE (policy_revision) ON public.orgs TO insightrag_runtime")

    ctx_user = "insightrag_security.context_user_id()"
    member = "insightrag_security.is_member(org_id)"
    _policy("security_users", "self_identity", "SELECT", f"id = {ctx_user} AND active")
    _policy("orgs", "member_read", "SELECT", "insightrag_security.is_member(id)")
    _policy(
        "orgs",
        "revision_update",
        "UPDATE",
        "insightrag_security.can_increment_revision(id)",
        "insightrag_security.can_increment_revision(id)",
    )
    _policy(
        "org_memberships",
        "membership_read",
        "SELECT",
        f"{member} AND (user_id = {ctx_user} OR insightrag_security.can_audit(org_id))",
    )
    _policy(
        "workspaces",
        "workspace_read",
        "SELECT",
        "insightrag_security.has_workspace_capability(org_id,id,'read')",
    )
    _policy(
        "workspace_memberships",
        "workspace_membership_read",
        "SELECT",
        f"{member} AND (user_id = {ctx_user} OR insightrag_security.can_audit(org_id))",
    )
    _policy("groups", "group_read", "SELECT", member)
    _policy(
        "group_memberships",
        "group_membership_read",
        "SELECT",
        f"{member} AND (user_id = {ctx_user} OR insightrag_security.can_audit(org_id))",
    )
    _policy(
        "resources",
        "resource_read",
        "SELECT",
        "insightrag_security.can_resource_metadata(org_id,id)",
    )
    _policy(
        "resources",
        "resource_create",
        "INSERT",
        check=f"insightrag_security.has_workspace_capability(org_id,workspace_id,'upload') AND created_by = {ctx_user} AND state = 'quarantine' AND deleted_at IS NULL AND NOT legal_hold AND object_key IS NULL AND classification <= insightrag_security.user_clearance() AND (NOT require_mfa OR insightrag_security.context_mfa()) AND (purpose IS NULL OR purpose = NULLIF(current_setting('app.purpose',true),''))",
    )
    _policy(
        "resources",
        "resource_update",
        "UPDATE",
        "insightrag_security.can_resource(org_id,id,'delete') OR insightrag_security.can_resource(org_id,id,'manage')",
        member,
    )
    _policy(
        "resource_grants",
        "grant_read",
        "SELECT",
        f"{member} AND (user_id = {ctx_user} OR insightrag_security.can_resource(org_id,resource_id,'manage') OR group_id IN (SELECT gm.group_id FROM public.group_memberships gm WHERE gm.org_id = resource_grants.org_id AND gm.user_id = {ctx_user}))",
    )
    _policy(
        "resource_grants",
        "grant_insert",
        "INSERT",
        check="insightrag_security.can_manage_grant(org_id,resource_id,user_id,group_id,action)",
    )
    _policy(
        "resource_grants",
        "grant_delete",
        "DELETE",
        "insightrag_security.can_resource(org_id,resource_id,'manage')",
    )
    _policy(
        "dataset_rows",
        "dataset_read",
        "SELECT",
        "insightrag_security.can_dataset_row(org_id,resource_id,region)",
    )
    _policy(
        "row_entitlements",
        "entitlement_read",
        "SELECT",
        f"{member} AND user_id = {ctx_user} AND insightrag_security.can_resource(org_id,resource_id,'query')",
    )
    _policy(
        "document_chunks",
        "chunk_read",
        "SELECT",
        "insightrag_security.can_resource(org_id,resource_id,'read')",
    )
    _policy(
        "audit_events",
        "audit_read",
        "SELECT",
        f"{member} AND (actor_id = {ctx_user} OR insightrag_security.can_audit(org_id))",
    )
    _policy("audit_events", "audit_append", "INSERT", check=f"{member} AND actor_id = {ctx_user}")
    job_scope = f"{member} AND requested_by = {ctx_user}"
    _policy("security_jobs", "job_read", "SELECT", job_scope)
    _policy(
        "security_jobs",
        "job_create",
        "INSERT",
        check=job_scope
        + " AND state = 'queued' AND policy_revision = (SELECT o.policy_revision FROM public.orgs o WHERE o.id = org_id) AND insightrag_security.can_job_resource(org_id,resource_id,action,object_key)",
    )
    _policy("security_jobs", "job_state", "UPDATE", job_scope, job_scope)
    op.execute("""CREATE FUNCTION insightrag_security.increasing_revision() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
        BEGIN
          IF NEW.policy_revision <= OLD.policy_revision THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Policy revision must increase';
          END IF;
          RETURN NEW;
        END $function$""")
    op.execute("REVOKE ALL ON FUNCTION insightrag_security.increasing_revision() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER increasing_policy_revision BEFORE UPDATE OF policy_revision ON public.orgs FOR EACH ROW EXECUTE FUNCTION insightrag_security.increasing_revision()"
    )
    op.execute("""CREATE FUNCTION insightrag_security.runtime_resource_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
        BEGIN
          IF current_user = 'insightrag_runtime' THEN
            IF NEW.state IS DISTINCT FROM OLD.state AND NEW.state <> 'deleted' THEN
              RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Runtime cannot publish resource';
            END IF;
            IF NEW.title IS DISTINCT FROM OLD.title AND NOT insightrag_security.can_resource(OLD.org_id,OLD.id,'manage') THEN
              RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Resource title requires manage capability';
            END IF;
          END IF;
          RETURN NEW;
        END $function$""")
    op.execute("REVOKE ALL ON FUNCTION insightrag_security.runtime_resource_mutation() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER runtime_resource_mutation BEFORE UPDATE ON public.resources FOR EACH ROW EXECUTE FUNCTION insightrag_security.runtime_resource_mutation()"
    )
    op.execute("""CREATE FUNCTION insightrag_security.default_resource_retention() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $function$
        BEGIN
          IF NEW.retention_until IS NULL THEN
            SELECT current_timestamp + o.retention_days * interval '1 day'
            INTO NEW.retention_until FROM public.orgs AS o WHERE o.id = NEW.org_id;
          END IF;
          RETURN NEW;
        END $function$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.default_resource_retention() FROM PUBLIC"
    )
    op.execute(
        "CREATE TRIGGER resource_retention_default BEFORE INSERT ON public.resources FOR EACH ROW EXECUTE FUNCTION insightrag_security.default_resource_retention()"
    )
    op.execute("""CREATE FUNCTION insightrag_security.job_state_transition() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
        BEGIN
          IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
            (OLD.state = 'queued' AND NEW.state IN ('running','completed','denied','held','failed'))
            OR (OLD.state = 'running' AND NEW.state IN ('completed','denied','held','failed'))
          ) THEN
            RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'Invalid security job transition';
          END IF;
          RETURN NEW;
        END $function$""")
    op.execute("REVOKE ALL ON FUNCTION insightrag_security.job_state_transition() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER security_job_state BEFORE UPDATE OF state ON public.security_jobs FOR EACH ROW EXECUTE FUNCTION insightrag_security.job_state_transition()"
    )
    # Policy revisions are a database invariant, including owner/CLI writes outside HTTP routes.
    op.execute("""CREATE FUNCTION insightrag_security.touch_org_policy_revision() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $function$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            UPDATE public.orgs SET policy_revision = policy_revision + 1 WHERE id = NEW.org_id;
          ELSIF TG_OP = 'DELETE' THEN
            UPDATE public.orgs SET policy_revision = policy_revision + 1 WHERE id = OLD.org_id;
          ELSIF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            UPDATE public.orgs SET policy_revision = policy_revision + 1
            WHERE id IN (OLD.org_id, NEW.org_id);
          END IF;
          RETURN NULL;
        END $function$""")
    op.execute("REVOKE ALL ON FUNCTION insightrag_security.touch_org_policy_revision() FROM PUBLIC")
    for table in (
        "org_memberships",
        "workspace_memberships",
        "groups",
        "group_memberships",
        "resource_grants",
        "row_entitlements",
    ):
        op.execute(
            f"CREATE TRIGGER invalidate_org_policy AFTER INSERT OR UPDATE OR DELETE ON public.{table} FOR EACH ROW EXECUTE FUNCTION insightrag_security.touch_org_policy_revision()"
        )
    op.execute(
        "CREATE TRIGGER invalidate_resource_policy AFTER INSERT OR DELETE OR UPDATE OF workspace_id,classification,require_mfa,state,purpose,legal_hold,retention_until,object_key,deleted_at,created_by ON public.resources FOR EACH ROW EXECUTE FUNCTION insightrag_security.touch_org_policy_revision()"
    )
    op.execute("""CREATE FUNCTION insightrag_security.touch_identity_policy_revision() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $function$
        BEGIN
          IF OLD.active IS DISTINCT FROM NEW.active OR OLD.clearance IS DISTINCT FROM NEW.clearance
             OR OLD.issuer IS DISTINCT FROM NEW.issuer OR OLD.subject IS DISTINCT FROM NEW.subject THEN
            UPDATE public.orgs AS o SET policy_revision = o.policy_revision + 1
            WHERE EXISTS (SELECT 1 FROM public.org_memberships AS m
                          WHERE m.org_id = o.id AND m.user_id IN (OLD.id, NEW.id));
          END IF;
          RETURN NULL;
        END $function$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.touch_identity_policy_revision() FROM PUBLIC"
    )
    op.execute(
        "CREATE TRIGGER invalidate_identity_policy AFTER UPDATE OF active,clearance,issuer,subject ON public.security_users FOR EACH ROW EXECUTE FUNCTION insightrag_security.touch_identity_policy_revision()"
    )
    op.execute("""CREATE FUNCTION insightrag_security.purge_deleted_resource(p_job uuid) RETURNS text
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $function$
        DECLARE
          v_job public.security_jobs%ROWTYPE;
          v_resource public.resources%ROWTYPE;
          v_revision bigint;
        BEGIN
          -- Share-lock the policy revision before authorization and destructive operations.
          -- Concurrent policy mutation triggers must wait until this transaction completes.
          SELECT o.policy_revision INTO v_revision FROM public.orgs AS o
          WHERE o.id = insightrag_security.context_org_id() FOR SHARE;
          IF NOT FOUND OR NOT insightrag_security.is_member(insightrag_security.context_org_id()) THEN
            RETURN 'denied';
          END IF;
          SELECT j.* INTO v_job FROM public.security_jobs AS j
          WHERE j.org_id = insightrag_security.context_org_id() AND j.id = p_job
            AND j.requested_by = insightrag_security.context_user_id() FOR UPDATE;
          IF NOT FOUND OR v_job.action <> 'delete' THEN RETURN 'denied'; END IF;
          IF v_job.policy_revision <> v_revision
             OR NOT insightrag_security.can_job_resource(v_job.org_id,v_job.resource_id,'delete',v_job.object_key) THEN
            IF v_job.state IN ('queued','running') THEN
              UPDATE public.security_jobs SET state = 'denied' WHERE org_id = v_job.org_id AND id = p_job;
            END IF;
            RETURN 'denied';
          END IF;
          IF v_job.state = 'completed' THEN RETURN 'completed'; END IF;
          IF v_job.state = 'held' THEN RETURN 'held'; END IF;
          IF v_job.state NOT IN ('queued','running') THEN RETURN 'denied'; END IF;
          SELECT r.* INTO v_resource FROM public.resources AS r
          WHERE r.org_id = v_job.org_id AND r.id = v_job.resource_id;
          IF NOT FOUND OR v_resource.state <> 'deleted' THEN
            UPDATE public.security_jobs SET state = 'denied' WHERE org_id = v_job.org_id AND id = p_job;
            RETURN 'denied';
          END IF;
          IF v_resource.legal_hold OR v_resource.retention_until > current_timestamp THEN
            UPDATE public.security_jobs SET state = 'held' WHERE org_id = v_job.org_id AND id = p_job;
            RETURN 'held';
          END IF;
          -- No blob provider exists in this phase. Never claim an object was purged.
          IF v_resource.object_key IS NOT NULL THEN RETURN 'pending_storage'; END IF;
          DELETE FROM public.document_chunks WHERE org_id = v_job.org_id AND resource_id = v_job.resource_id;
          DELETE FROM public.dataset_rows WHERE org_id = v_job.org_id AND resource_id = v_job.resource_id;
          UPDATE public.security_jobs SET state = 'completed' WHERE org_id = v_job.org_id AND id = p_job;
          RETURN 'completed';
        END $function$""")
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.purge_deleted_resource(uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.purge_deleted_resource(uuid) TO insightrag_runtime"
    )
    # PostgreSQL applies UPDATE RLS to locking SELECTs. This narrow helper lets a
    # viewer lock only their active organization's revision without a write policy.
    op.execute(LOCK_MEMBER_REVISION_SQL)
    op.execute(
        "REVOKE ALL ON FUNCTION insightrag_security.lock_member_policy_revision(uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION insightrag_security.lock_member_policy_revision(uuid) TO insightrag_runtime"
    )
    op.execute("UPDATE platform_metadata SET value = 'phase3' WHERE key = 'schema_version'")


def downgrade() -> None:
    # Drop policies/tables first; the cluster-wide NOLOGIN reader role may be used by another DB.
    op.execute("DROP FUNCTION insightrag_security.purge_deleted_resource(uuid)")
    op.execute("DROP TRIGGER increasing_policy_revision ON public.orgs")
    op.execute("DROP TRIGGER runtime_resource_mutation ON public.resources")
    op.execute("DROP TRIGGER security_job_state ON public.security_jobs")
    for table in (
        "security_jobs",
        "audit_events",
        "row_entitlements",
        "document_chunks",
        "dataset_rows",
        "resource_grants",
        "resources",
        "group_memberships",
        "workspace_memberships",
        "groups",
        "workspaces",
        "org_memberships",
        "orgs",
        "security_users",
    ):
        op.execute(f"DROP TABLE public.{table}")
    op.execute("DROP SCHEMA insightrag_security CASCADE")
    op.execute("UPDATE platform_metadata SET value = 'phase2' WHERE key = 'schema_version'")
