# Phase 2 technical interview preparation

Each domain includes five model answers, a system-design exercise and a debugging scenario. Refer to the implemented code and [actual verification](../testing/phase-02-verification.md), not claims about a deployed enterprise platform. Frontend-specific questions are in the [web guide](../modules/web-foundation.md).

## FastAPI, ASGI and contracts

1. **What does ASGI provide?** A server/application interface using scope, receive and send with asynchronous execution. Uvicorn speaks network HTTP; FastAPI/Starlette route protocol events to handlers. ASGI does not make blocking Python code nonblocking.
2. **System design: how do requests traverse this API?** Server -> request context -> routing/dependencies -> Pydantic validation -> handler -> response validation/serialization -> ASGI response. Lifespan manages process-owned clients; request context manages correlation, not identity.
3. **Debugging: why does an async endpoint block all requests?** Inspect synchronous I/O, CPU work and blocking helper calls executed directly inside the coroutine. Await proper async drivers; move unsafe/CPU work into bounded worker processes. More async syntax alone changes nothing.
4. **Why validate both requests and responses?** Input constraints reject invalid caller data; response contracts catch implementation drift and define OpenAPI. Neither replaces authorization or factual correctness. Validation errors must omit rejected sensitive values.
5. **How does versioning help compatibility?** `/api/v1` establishes a contract namespace; additive changes still require compatibility review. Health checks remain operational paths. A changed metric meaning can be breaking even if JSON fields stay the same.

## Async execution, lifespan and DI

1. **What happens while awaiting asyncpg?** The coroutine yields while socket I/O is pending so the event loop can advance other work. CPU parallelism needs processes/appropriate execution resources; asynchronous concurrency is not unlimited capacity.
2. **System design: where should clients live?** Engines/Redis clients belong to application lifespan per process; sessions belong to requests/tasks. Dependencies retrieve these resources and expose a testable construction boundary. Startup/shutdown are exercised by context-managed tests.
3. **Debugging: why do transport-only tests lack app.state.database?** HTTP transport may not drive ASGI lifespan. Enter TestClient as a context or use LifespanManager; do not hide missing startup with production mock defaults.
4. **When does FastAPI use a thread pool?** Ordinary def path functions/dependencies are dispatched through its sync execution support. A normal helper called inside async code runs directly; it is not automatically offloaded. Use explicit bounded offloading when necessary.
5. **Why use pure ASGI middleware here?** It wraps events without buffering content and preserves explicit context handling across normal/exception responses. The finally block resets ContextVar tokens to avoid correlation leakage; error handlers also use request.state for outer server-error paths.

## SQLAlchemy, pooling and transactions

1. **Engine versus session?** The engine owns connectivity/pooling. AsyncSession is mutable transactional unit-of-work state. One process can share an engine; concurrent requests/tasks must not share a session.
2. **System design: how do you size DB connections?** Budget processes times pool_size+overflow, plus workers/migrations/other clients, below server capacity. Measure pool wait and query time separately; admission control prevents unbounded requests waiting for connections.
3. **Debugging: why does pre-ping not save a transaction?** It validates before checkout, not throughout execution. A disconnect mid-transaction loses that transaction; any retry needs explicit idempotency and rollback semantics, not automatic repetition of unknown effects.
4. **Why explicit commit boundaries?** Closing a session rolls back uncommitted work. Business services know which changes must be atomic; a generic dependency committing every response can hide failures or commit unexpected effects.
5. **Why not hold a transaction during an LLM call?** External latency pins a scarce connection and possibly locks while doing no database work. Fetch permitted versioned evidence, release resources, then reauthorize/revalidate before final effects or disclosure.

## Alembic and database roles

1. **What does a migration add beyond ORM models?** An ordered, reviewable change history and a controlled method to evolve existing databases. A model describes desired mapping; it does not safely migrate production history on its own.
2. **System design: why a separate migration process?** Multiple API replicas must not race DDL. A one-shot owner process runs before ready services; runtime uses restricted credentials and cannot migrate. Expand/contract supports compatible deployment transitions.
3. **Debugging: live passes but readiness fails after deployment. What do you inspect?** Dependency reachability, runtime SELECT grants, platform schema value and Alembic revision. Do not expose raw SQL/credential details in the readiness response.
4. **What is run_sync doing?** It bridges Alembic's synchronous migration operations onto SQLAlchemy's async connection within a dedicated async migration program. It is not permission to call asyncio.run from a live request event loop.
5. **Is downgrade always safe?** No: schema rollback may lose data or be incompatible with deployed code. Test only in disposable environments and design forward recovery/compatibility. This phase's shared integration test repeats upgrade; isolated native testing may separately exercise downgrade.

## Configuration, logging and security

1. **Does SecretStr secure a credential?** It masks common representation, not storage or memory. The credential still reaches drivers through get_secret_value. File/secret-service access, logging discipline, TLS and rotation are separate responsibilities.
2. **System design: how do you correlate failures without leaking inputs?** Accept/generate canonical request UUIDs, bind ContextVars, log route templates/status/timing and safe error codes, return the same ID. Exclude raw URLs, bodies, secret-bearing exception strings and unrestricted vendor logs.
3. **Debugging: sanitized 500 responses still leak secrets in logs. Why?** Starlette can re-raise after returning the error, letting Uvicorn print exception details. Centralize safe stdlib formatting/propagation as well as application error handling; test both with secret canaries.
4. **Why reject simultaneous URL and URL_FILE?** Ambiguous precedence can silently use stale or unintended credentials. Fail early with a safe configuration error and require a single source. Missing production dependencies also fail configuration.
5. **Why no tenant routes yet?** Until identity, memberships, transaction context and RLS are implemented, a route could expose data without a trustworthy boundary. Phase 2 demonstrates contracts using non-sensitive metadata and development-only echo.

## Redis, Celery and background processes

1. **Broker versus result backend?** The broker transports task messages; a backend stores task outcomes. Redis can fill both roles here, but neither is the durable future business-job registry. Results expire and contain diagnostic status only.
2. **System design: how would you turn this diagnostic into ingestion infrastructure?** Add PostgreSQL job/outbox intent, stable operation keys, payload hashes, leases/fencing, receipts, classified retries and reconciliation before accepting tenant work. Preserve the existing worker capability boundary.
3. **Debugging: eager task passes but worker never receives messages. What do you inspect?** Broker URL/credentials, Compose DNS, queue names, worker registration, serializer acceptance and actual send/result round trip. Eager tests bypass the broker entirely.
4. **What does acks-late guarantee?** Acknowledgement occurs after processing in ordinary cases, but crashes/requeues can repeat execution. It does not guarantee exactly-once effects or eliminate all lost-work cases; use durable application state.
5. **Why JSON-only and bounded prefetch?** Rejecting arbitrary serialized Python reduces unsafe deserialization surface. Low prefetch and concurrency limits improve fairness but need workload tuning; time limits do not replace per-I/O deadlines and idempotency.

## Docker, CI/CD and dependency assurance

1. **System design: how do Compose services find each other?** Containers use service DNS names such as postgres/redis on their network. Host clients use loopback-published ports. localhost inside the API container refers to that container, not PostgreSQL.
2. **Why health-gated startup?** Process existence does not imply accepting requests or migrated schema. Dependencies can still fail later, so runtime readiness/timeouts remain necessary even after Compose conditions succeed.
3. **Debugging: credentials changed but PostgreSQL rejects them. Why?** Existing volumes retain initialized roles/passwords; regenerating local secret files alone does not rotate database state. Bootstrap preserves files; rotation must update both sides through a controlled procedure.
4. **What do lockfiles and vulnerability scans prove?** Locks make resolution reproducible and record hashes; scans report known issues from a database at a time. Neither proves absence of vulnerabilities. Review upgrades; do not use force-fix to downgrade or break runtime dependencies silently.
5. **What is implemented CI versus CD?** CI defines reproducible checks, integration services, audits and container smoke after checkout. No hosted run is claimed until executed. Deployment to a production environment, approvals, release rollback and credentials are future CD work.
