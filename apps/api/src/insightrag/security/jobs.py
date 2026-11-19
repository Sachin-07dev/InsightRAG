"""Signed operator-dispatched deletion work with fresh DB authorization.

Only the trusted API/operator tier can mint these identities. The signature is
never a replacement for the current durable job and RLS checks below.
"""

import argparse
import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import text

from insightrag.core.config import Settings
from insightrag.db.session import Database
from insightrag.ingestion.service import configured_store
from insightrag.security.context import AccessContext
from insightrag.security.controls import (
    ControlUnavailable,
    JobClaims,
    SignedJobEnvelope,
    assert_object_scope,
)
from insightrag.security.database import tenant_session
from insightrag.security.dependencies import audit


async def load_job_context(
    database: Database, claims: JobClaims
) -> tuple[AccessContext, str] | None:
    preliminary = AccessContext(
        user_id=claims.user_id,
        organization_id=claims.organization_id,
        role="viewer",
        clearance=0,
        mfa=False,
        policy_revision=claims.policy_revision,
        request_id=str(uuid4()),
        purpose="deletion",
    )
    async with tenant_session(database, preliminary) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT m.role,u.clearance,o.policy_revision,"
                        "j.state,j.resource_id,j.action "
                        "FROM org_memberships m JOIN security_users u ON u.id=m.user_id "
                        "JOIN orgs o ON o.id=m.org_id JOIN security_jobs j ON j.org_id=o.id "
                        "AND j.requested_by=u.id WHERE m.org_id=:org AND m.user_id=:user "
                        "AND m.status='active' AND u.active AND j.id=:job"
                    ),
                    {"org": claims.organization_id, "user": claims.user_id, "job": claims.job_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["resource_id"] != claims.resource_id or row["action"] != "delete":
            return None
        if row["policy_revision"] != claims.policy_revision:
            return None
        return replace(preliminary, role=row["role"], clearance=row["clearance"]), row["state"]


async def run_security_job(token: str, settings: Settings) -> dict[str, str]:
    if settings.signed_job_key is None or settings.redis_url is None:
        raise ControlUnavailable("Signed worker identity is not configured")
    envelopes = SignedJobEnvelope(settings.signed_job_key.get_secret_value().encode())
    claims = envelopes.verify(token)
    database = Database(settings)
    redis: Redis = Redis.from_url(
        settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
    )
    try:
        loaded = await load_job_context(database, claims)
        if loaded is None:
            return {"state": "denied"}
        context, state = loaded
        if state in {"completed", "held", "denied", "failed"}:
            return {"state": state}
        # Consume the nonce outside a DB transaction. The DB effect is separately idempotent.
        await envelopes.verify_once(token, redis)
        async with tenant_session(database, context) as session:
            result = await session.scalar(
                text("SELECT insightrag_security.purge_deleted_resource(:job)"),
                {"job": claims.job_id},
            )
            if result not in {"completed", "held", "denied", "pending_storage"}:
                raise ControlUnavailable("Unexpected deletion result")
            keys = None
            if result == "pending_storage":
                keys = await session.scalar(
                    text("SELECT insightrag_security.ingestion_deletion_keys(:job)"),
                    {"job": claims.job_id},
                )
            await audit(session, context, "deletion." + result, claims.resource_id)
        if result == "pending_storage":
            if keys is None:
                return {"state": "denied"}
            store = configured_store(settings)
            if store is None:
                return {"state": "pending_storage"}
            for key in keys:
                parts = key.split("/")
                if (
                    len(parts) != 9
                    or parts[4] != "resources"
                    or parts[5] != str(claims.resource_id)
                ):
                    raise ControlUnavailable("Storage key is outside the deletion scope")
                assert_object_scope(key, claims.organization_id, UUID(parts[3]))
                await store.delete(key)
            async with tenant_session(database, context) as session:
                result = await session.scalar(
                    text("SELECT insightrag_security.finish_ingestion_deletion(:job)"),
                    {"job": claims.job_id},
                )
                if result not in {"completed", "denied", "held", "pending_storage"}:
                    raise ControlUnavailable("Unexpected deletion completion result")
                await audit(session, context, "deletion." + result, claims.resource_id)
        return {"state": result}
    finally:
        await redis.aclose()
        await database.close()


async def dispatch_job(settings: Settings, organization: UUID, actor: UUID, job_id: UUID) -> str:
    """Trusted operator integration, not a public unauthenticated endpoint."""
    if settings.signed_job_key is None:
        raise ControlUnavailable("Signed worker identity is not configured")
    database = Database(settings)
    try:
        scope = AccessContext(
            actor, organization, "viewer", 0, False, 1, str(uuid4()), purpose="deletion"
        )
        async with tenant_session(database, scope) as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT j.resource_id,j.policy_revision,j.state FROM security_jobs j "
                            "WHERE j.org_id=:org AND j.id=:job AND j.requested_by=:actor"
                        ),
                        {"org": organization, "job": job_id, "actor": actor},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["state"] not in {"queued", "running"}:
                raise ControlUnavailable("Job is unavailable for dispatch")
            envelope = SignedJobEnvelope(settings.signed_job_key.get_secret_value().encode()).issue(
                organization, actor, job_id, row["resource_id"], row["policy_revision"]
            )
        from insightrag.worker import create_celery

        worker = create_celery(settings)
        try:
            result = await asyncio.to_thread(
                worker.send_task,
                "insightrag.security.execute",
                args=[envelope],
                argsrepr="(<redacted>,)",
                kwargsrepr="{}",
            )
            return str(result.id)
        finally:
            worker.close()
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch a preauthorized durable security job")
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--actor-id", type=UUID, required=True)
    parser.add_argument("--job-id", type=UUID, required=True)
    args = parser.parse_args()
    task_id = asyncio.run(
        dispatch_job(Settings(), args.organization_id, args.actor_id, args.job_id)
    )
    print(f"Dispatched security job as task {task_id}; no token or credential printed")


if __name__ == "__main__":
    main()
