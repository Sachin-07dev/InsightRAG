"""JSON events with an explicit field boundary and sanitized vendor logs.

Uvicorn re-logs exceptions after an ASGI error response. Consequently a safe HTTP
handler alone cannot prevent leaked exception text in the server's own logger.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import structlog

_APPLICATION_EVENTS = {"http_request", "unhandled_error", "rag_query_completed"}
_APPLICATION_FIELDS = {
    "event",
    "level",
    "timestamp",
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "error_type",
    "candidate_count",
    "citation_count",
    "rag_status",
    "embedding_ms",
    "dense_ms",
    "sparse_ms",
    "fusion_ms",
    "rerank_ms",
    "context_ms",
    "generation_ms",
    "recheck_ms",
    "prompt_tokens",
    "completion_tokens",
}


class SafeJsonFormatter(logging.Formatter):
    """Never interpolate third-party messages, arguments or exception text.

    Trusted application events have a deliberately narrow schema. New events or
    fields require review before addition; foreign messages retain severity,
    logger and exception class but omit arbitrary URLs, payloads and tracebacks.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": "runtime_log",
        }
        if isinstance(record.msg, dict) and record.msg.get("event") in _APPLICATION_EVENTS:
            payload.update(
                {key: value for key, value in record.msg.items() if key in _APPLICATION_FIELDS}
            )
        else:
            if record.exc_info and record.exc_info[0]:
                payload["error_type"] = record.exc_info[0].__name__
            request_id = structlog.contextvars.get_contextvars().get("request_id")
            if request_id is not None:
                payload["request_id"] = request_id
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # Uvicorn configures its own handlers before lifespan starts. Replace those
    # paths so re-raised ASGI exceptions cannot bypass the safe JSON formatter.
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "celery",
        "celery.task",
        "celery.redirected",
    ):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
