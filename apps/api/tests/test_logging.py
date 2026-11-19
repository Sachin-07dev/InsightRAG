"""Regression checks for secret-bearing framework and application log paths."""

import io
import json
import logging
import sys

import structlog
from insightrag.core.logging import SafeJsonFormatter, configure_logging


def test_vendor_exception_omits_message_traceback_and_args() -> None:
    secret = "synthetic-secret-must-never-be-logged"
    try:
        raise RuntimeError(f"postgresql://user:{secret}@db/private")
    except RuntimeError:
        record = logging.LogRecord(
            "uvicorn.error",
            logging.ERROR,
            __file__,
            1,
            "ASGI exception %s",
            (secret,),
            sys.exc_info(),
        )
    output = SafeJsonFormatter().format(record)
    assert secret not in output
    assert "postgresql" not in output
    assert "ASGI exception" not in output
    assert json.loads(output)["error_type"] == "RuntimeError"


def test_plain_vendor_url_is_not_interpolated() -> None:
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "Request to %s",
        ("https://user:synthetic-secret@host/private",),
        None,
    )
    output = SafeJsonFormatter().format(record)
    assert "synthetic-secret" not in output
    assert json.loads(output)["event"] == "runtime_log"


def test_application_events_drop_unapproved_fields() -> None:
    record = logging.LogRecord(
        "insightrag",
        logging.INFO,
        __file__,
        1,
        {
            "event": "http_request",
            "method": "POST",
            "route": "/api/v1/diagnostics/echo",
            "status": 200,
            "password": "synthetic-secret",
            "body": "synthetic-secret",
            "exc_info": "synthetic-secret",
        },
        (),
        None,
    )
    output = SafeJsonFormatter().format(record)
    assert "synthetic-secret" not in output
    payload = json.loads(output)
    assert payload["status"] == 200
    assert payload["route"] == "/api/v1/diagnostics/echo"


def test_configured_uvicorn_handler_cannot_bypass_redaction() -> None:
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    logger = logging.getLogger("uvicorn.error")
    logger_state = (logger.handlers[:], logger.level, logger.propagate)
    structlog_state = structlog.get_config()
    output = io.StringIO()
    try:
        configure_logging()
        root.handlers[0].setStream(output)  # type: ignore[attr-defined]
        try:
            raise RuntimeError("synthetic-secret")
        except RuntimeError:
            logger.exception("Exception in ASGI application: synthetic-secret")
        lines = output.getvalue().splitlines()
        assert len(lines) == 1
        assert "synthetic-secret" not in lines[0]
        assert json.loads(lines[0])["error_type"] == "RuntimeError"
    finally:
        root.handlers, root.level = original_handlers, original_level
        logger.handlers, logger.level, logger.propagate = logger_state
        structlog.configure(**structlog_state)
