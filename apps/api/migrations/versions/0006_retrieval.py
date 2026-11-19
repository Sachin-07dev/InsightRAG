"""Index lexical evidence and isolate persisted conversations."""
# ruff: noqa: E501

from alembic import op

revision = "0006_retrieval"
down_revision = "0005_reindex"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ingestion_chunks_fts ON public.ingestion_chunks USING gin (to_tsvector('english'::regconfig, text))"
    )
    op.execute("""CREATE TABLE public.rag_conversations (
      org_id uuid NOT NULL, id uuid NOT NULL, workspace_id uuid NOT NULL, owner_id uuid NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(org_id,id),
      FOREIGN KEY(org_id,workspace_id) REFERENCES public.workspaces(org_id,id),
      FOREIGN KEY(org_id,owner_id) REFERENCES public.org_memberships(org_id,user_id)
    )""")
    op.execute("""CREATE TABLE public.rag_turns (
      org_id uuid NOT NULL, conversation_id uuid NOT NULL, id uuid NOT NULL,
      question text NOT NULL, outcome text NOT NULL, citation_refs jsonb NOT NULL DEFAULT '[]',
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(org_id,conversation_id,id),
      FOREIGN KEY(org_id,conversation_id) REFERENCES public.rag_conversations(org_id,id) ON DELETE CASCADE,
      CHECK(length(question) BETWEEN 3 AND 1000),
      CHECK(outcome IN ('answered','abstained'))
    )""")
    for table in ("rag_conversations", "rag_turns"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
        op.execute(f"GRANT SELECT,INSERT ON public.{table} TO insightrag_runtime")
    op.execute("""CREATE POLICY conversation_owner ON public.rag_conversations TO insightrag_runtime
      USING(org_id=insightrag_security.context_org_id() AND owner_id=insightrag_security.context_user_id()
        AND insightrag_security.is_member(org_id) AND EXISTS(
          SELECT 1 FROM public.workspace_memberships m WHERE m.org_id=rag_conversations.org_id
          AND m.workspace_id=rag_conversations.workspace_id AND m.user_id=rag_conversations.owner_id))
      WITH CHECK(org_id=insightrag_security.context_org_id() AND owner_id=insightrag_security.context_user_id()
        AND insightrag_security.is_member(org_id) AND EXISTS(
          SELECT 1 FROM public.workspace_memberships m WHERE m.org_id=rag_conversations.org_id
          AND m.workspace_id=rag_conversations.workspace_id AND m.user_id=rag_conversations.owner_id))""")
    op.execute("""CREATE POLICY turn_owner ON public.rag_turns TO insightrag_runtime
      USING(EXISTS(SELECT 1 FROM public.rag_conversations c WHERE c.org_id=rag_turns.org_id
        AND c.id=rag_turns.conversation_id))
      WITH CHECK(EXISTS(SELECT 1 FROM public.rag_conversations c WHERE c.org_id=rag_turns.org_id
        AND c.id=rag_turns.conversation_id))""")
    op.execute("UPDATE public.platform_metadata SET value='phase5' WHERE key='schema_version'")


def downgrade() -> None:
    op.execute("DROP TABLE public.rag_turns")
    op.execute("DROP TABLE public.rag_conversations")
    op.execute("DROP INDEX public.ingestion_chunks_fts")
    op.execute("UPDATE public.platform_metadata SET value='phase4' WHERE key='schema_version'")
