"""JSON-only diagnostics and signed, reauthorized security cleanup tasks."""

import asyncio
from typing import Any

from celery import Celery
from celery.signals import setup_logging

from insightrag.core.config import Settings
from insightrag.core.logging import configure_logging


def diagnostic_ping() -> dict[str, str]:
    """Same callable in every factory instance; no external side effects."""
    return {"status": "ok"}


def security_execute(envelope: str) -> dict[str, str]:
    from insightrag.security.jobs import run_security_job

    return asyncio.run(run_security_job(envelope, Settings()))


def ingestion_execute(envelope: str) -> dict[str, str]:
    from insightrag.ingestion.service import run_ingestion_job

    return asyncio.run(run_ingestion_job(envelope, Settings()))


def create_celery(settings: Settings) -> Any:
    if not settings.redis_url:
        raise RuntimeError("Worker requires Redis configuration")
    url = settings.redis_url.get_secret_value()
    worker = Celery("insightrag", broker=url, backend=url)
    worker.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_default_queue="foundation",
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_time_limit=30,
        task_soft_time_limit=20,
        result_expires=60,
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=5,
        broker_connection_timeout=3,
        task_publish_retry=False,
        broker_transport_options={"visibility_timeout": 60},
        timezone="UTC",
        enable_utc=True,
        worker_hijack_root_logger=False,
    )

    worker.task(name="insightrag.diagnostics.ping", ignore_result=False)(diagnostic_ping)
    worker.task(name="insightrag.security.execute", ignore_result=False)(security_execute)
    worker.task(
        name="insightrag.ingestion.execute",
        ignore_result=False,
        soft_time_limit=240,
        time_limit=270,
    )(ingestion_execute)

    return worker


@setup_logging.connect
def setup_worker_logging(**kwargs: Any) -> None:
    configure_logging(Settings().log_level)


celery_app = create_celery(Settings())
