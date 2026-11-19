"""Trusted operator redispatch for queued, failed or abandoned ingestion jobs."""

import argparse
import asyncio
from uuid import UUID, uuid4

from sqlalchemy import text

from insightrag.core.config import Settings
from insightrag.db.session import Database
from insightrag.security.context import AccessContext
from insightrag.security.controls import ControlUnavailable, SignedJobEnvelope
from insightrag.security.database import require_resource, tenant_session


async def dispatch_job(settings: Settings, organization: UUID, actor: UUID, job_id: UUID) -> str:
    if not settings.signed_job_key or not settings.redis_url:
        raise ControlUnavailable("Signed worker dispatch is unavailable")
    database = Database(settings)
    try:
        scope = AccessContext(actor, organization, "viewer", 0, False, 1, str(uuid4()))
        async with tenant_session(database, scope) as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT j.resource_id,j.policy_revision,j.state,"
                            "o.policy_revision AS current_revision "
                            "FROM ingestion_jobs j JOIN orgs o ON o.id=j.org_id "
                            "WHERE j.org_id=:org AND j.id=:job AND j.requested_by=:actor"
                        ),
                        {"org": organization, "job": job_id, "actor": actor},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["state"] not in ("queued", "running", "failed")
                or (row["policy_revision"] != row["current_revision"])
            ):
                raise ControlUnavailable("Ingestion job is unavailable for redispatch")
            await require_resource(session, scope, row["resource_id"], "upload")
            token = SignedJobEnvelope(settings.signed_job_key.get_secret_value().encode()).issue(
                organization, actor, job_id, row["resource_id"], row["policy_revision"]
            )
        from insightrag.worker import create_celery

        celery = create_celery(settings)
        try:
            result = await asyncio.to_thread(
                celery.send_task,
                "insightrag.ingestion.execute",
                args=[token],
                argsrepr="(<redacted>,)",
            )
            return str(result.id)
        finally:
            celery.close()
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Redispatch a preauthorized ingestion job")
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--actor-id", type=UUID, required=True)
    parser.add_argument("--job-id", type=UUID, required=True)
    args = parser.parse_args()
    task_id = asyncio.run(
        dispatch_job(Settings(), args.organization_id, args.actor_id, args.job_id)
    )
    print(f"Dispatched ingestion task {task_id}")


if __name__ == "__main__":
    main()
