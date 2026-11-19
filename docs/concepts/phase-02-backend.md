# Phase 2 backend internals and code walkthrough

## ASGI and the FastAPI lifecycle

ASGI is the async application/server protocol: the server calls an application with `scope`, `receive` and `send`. `scope` describes a connection/request; message functions exchange body and response events. Uvicorn handles sockets/HTTP and drives this protocol. FastAPI builds routing, dependency resolution, Pydantic validation and OpenAPI atop Starlette. A browser does not call an async Python function directly.

```mermaid
sequenceDiagram
    participant Client
    participant Server as Uvicorn / ASGI
    participant Context as Request context
    participant Router as Router and dependencies
    participant Handler
    Client->>Server: HTTP request
    Server->>Context: scope, receive, send
    Context->>Router: Bind request ID; wrap send
    Router->>Router: Resolve dependencies and validate input
    Router->>Handler: Typed arguments
    Handler-->>Router: Typed result or exception
    Router-->>Context: Validated serialized response
    Context-->>Server: Headers/status + response events
    Server-->>Client: HTTP response
```

`main.create_app(settings)` returns a FastAPI instance. The nested lifespan context creates process-owned Database/Redis clients, exposes them in app.state, yields to serve traffic, then closes Redis and disposes the engine. Clients are lazy: startup need not wait for dependency recovery, while readiness reports availability. Tests must enter lifespan (TestClient context or LifespanManager) rather than assuming HTTPX transport runs startup automatically.

`main.app = create_app()` is the import target for Uvicorn. Import validates configuration but creates no network connections. Production requires DB/Redis configuration and does not register docs/echo. No application startup runs DDL.

## Async versus sync, internally

`async def` does not create a thread or make blocking code nonblocking. Awaiting asyncpg/Redis I/O yields to the event loop; another request can run while the socket waits. A blocking parser, synchronous HTTP call or CPU-heavy transformation inside async code stalls that loop. FastAPI runs ordinary `def` routes/dependencies in a thread pool; ordinary helper functions called directly receive no automatic conversion. Use approved async libraries for I/O and bounded worker processes for heavy/unsafe work. Increasing API processes multiplies memory and pools.

`health.dependency_status(check, budget_seconds)` wraps an awaitable check in `asyncio.timeout`; timeout becomes a safe label, arbitrary exceptions become unavailable, and cancellation of the surrounding task is not swallowed by a broad BaseException catch. `check_dependencies` runs DB and Redis concurrently with gather, so latency is bounded near the slowest probe rather than their sum. No dependency exception string becomes response content.

## Dependency injection and connection pooling

`Database(settings)` creates one AsyncEngine per process with size/overflow/timeout limits, pre-ping, hidden SQL parameters and asyncpg command/connect timeouts. Engine creation is not a connection. `get_session(request)` is an async-generator dependency yielding one AsyncSession from the application factory; async context exit closes/rolls back uncommitted work. Business services must explicitly choose transaction commit boundaries. `expire_on_commit=False` avoids unexpected post-commit ORM loading, but does not make stale objects fresh or safe to share.

Future routes can use FastAPI Depends(get_session); tests can override dependencies without production mocks. Dependency injection expresses construction/lifetime and test substitution; it is not authentication. No tenant/session context is fabricated in Phase 2. Each concurrent task needs its own session; a transaction cannot safely carry two users' changing identity.

Pool budgeting: four API processes at defaults can open up to 40 connections, plus migrations/other clients. Pool wait time and query execution time are distinct. Never keep a connection checked out during external model calls. Pre-ping checks a connection before reuse; it does not retry a failed transaction or preserve its effects.

## Contracts, errors and correlation

`api/contracts.py` defines extra-forbidden Pydantic models. EchoRequest.message is a strict string of 1-128 characters; JSON numbers are not coerced into text. PlatformInfo reports only public service metadata. Readiness uses fixed labels. ErrorResponse carries safe code/message/request_id and ValidationIssue location/kind. Monetary/business contracts are intentionally not invented here.

`api/v1/routes.py` mounts versioned routes at `/api/v1`; `/health/*` is operational and independent of business API versioning. Echo uses `Annotated[str, Depends(get_request_id)]`: FastAPI resolves the request-scoped dependency in `api/dependencies.py` before invoking the handler. It supplies middleware correlation state, not authenticated identity. FastAPI generates schema from routes/models at `/api/v1/openapi.json` in development/test. A schema is a machine-readable contract, not a guarantee every security behavior is documented.

`RequestContextMiddleware` is pure ASGI. It canonicalizes a valid incoming UUID or generates one, stores it in scope state, binds ContextVar logging metadata, and wraps response-start to set correlation/no-store/nosniff headers. The `finally` block logs only a route template, status and duration, then restores prior ContextVar tokens. This prevents request IDs leaking between concurrent tasks; it never logs body/query/header content.

`errors.register_exception_handlers` maps validation, HTTP and unhandled exceptions to safe responses. Rejected values, SQL engine strings and tracebacks are omitted. The generic server-error layer can run after middleware resets context, so it retrieves request_id from request.state and explicitly sets the response header. Starlette can re-raise after sending a 500; sanitizing responses alone therefore does not sanitize Uvicorn logs.

`SafeJsonFormatter` emits an allowlisted application event schema. Vendor messages retain logger/severity/exception type, not interpolated arbitrary message/args/traceback. `configure_logging` reconfigures Uvicorn/Celery propagation so sensitive exception strings cannot bypass that boundary after lifespan starts. Safe structured error codes can be added deliberately; the tradeoff is less free-form debugging detail. Never log an entire Settings model or raw input just because it is inside an error handler.

## Configuration and secrets

`core/config.py` uses Pydantic Settings with INSIGHTRAG_ prefix, environment values and optional ignored `.env.local`. Direct URL and corresponding `_FILE` are mutually exclusive. File reads occur during startup configuration, not every request. SecretStr masks normal representation; it is not encryption and `.get_secret_value()` must stay inside trusted connection setup. PostgreSQL URLs require asyncpg driver; production refuses missing dependencies. Secret-file errors never echo contents. Production TLS/identity/secret-service requirements remain deployment policy, not implemented by SecretStr.

Migration credentials are separate from runtime credentials. The runtime has no CREATE/INSERT permission on foundation metadata. No health endpoint returns hosts/passwords or schema error traces. Operator-generated files under ignored `.secrets/` are local development capabilities; do not commit or image-copy them.

## Migrations, step by step

`alembic.ini` locates migrations relative to itself and contains no URL. `migrations/env.py` reads the migration URL, creates a NullPool async engine, and calls Alembic's synchronous migration operations through connection.run_sync. It uses asyncio.run as a standalone process, not inside a request event loop. Offline mode emits SQL without connecting. The template supports new revision files; no ORM autogeneration is claimed while target_metadata is None.

`0001_foundation.py` creates public.platform_metadata with a schema-version row. Alembic owns its own revision table. If the configured local runtime role exists, it receives SELECT only on those two tables. No tenant tables or unprotected tenant rows are created. Upgrade is version-tracked; repeated upgrade head is idempotent. Downgrade is tested only in a dedicated disposable database, never as an automatic operation on an arbitrary shared test database. Expand/migrate/contract becomes necessary as real schema appears.

## Redis, Celery and processes

`worker.create_celery(settings)` constructs a separately running Celery application with authenticated Redis broker/backend, JSON serializers and accepted content, bounded prefetch/time/retry settings, UTC and short result expiry. `diagnostic_ping()` is the same pure callable across factory instances and returns status only. Eager unit tests prove callable/configuration behavior, not actual broker delivery. CI submits a real task and waits for its result in Compose.

Redis is not a durable source of accepted future business-job intent. Phase 4 adds PostgreSQL jobs/outbox, stable operation keys, receipts and fencing. Acks-late/requeue settings can repeat execution; they do not imply exactly-once effects. Windows native development may use Celery solo; production execution targets Linux containers with process concurrency.

## Dependencies and alternatives

FastAPI handles HTTP/DI/schema; Pydantic validates contracts; pydantic-settings loads config; Uvicorn serves ASGI; SQLAlchemy handles pooling/transactions; asyncpg speaks PostgreSQL; Alembic versions schema; Redis client handles broker/probes; Celery executes jobs; structlog carries structured application events. Each exists for a present foundation requirement. LangGraph, LLM SDKs, OCR, S3 and chart engines are not added to backend dependencies without a feature needing them.

Ruff checks/formats Python; mypy checks source contracts; pytest/pytest-asyncio cover sync/async behavior; HTTPX and asgi-lifespan drive tests; PyYAML enables static infra parsing; pip-audit queries package vulnerability evidence. Locking prevents drift, not vulnerabilities. The selected Starlette test client emits an HTTPX deprecation notice; tests remain passing, and a compatible test-client upgrade should be evaluated rather than suppressing warnings blindly.

## Production and improvement

Monitor safe stage/error codes, pool wait, DB/Redis timeouts, queue age and schema mismatch. Actual OTEL export, tenant audit, SSO/RLS, durable jobs and deployment hardening are future work. Add them at their phase gates rather than representing this scaffolding as a finished enterprise platform. See [Phase 2 interviews](../interview/phase-02.md).

Primary references: [FastAPI async](https://fastapi.tiangolo.com/async/), [lifespan](https://fastapi.tiangolo.com/advanced/events/), [SQLAlchemy async sessions](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [Alembic async integration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic), [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
