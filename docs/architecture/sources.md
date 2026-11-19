# Primary technical source register

Reviewed for architecture on 2026-11-16. Documentation links may advance; record selected dependency versions and relevant behavior during implementation. References support technical behavior, not the proposed capacity/SLO numbers.

| Source | Architectural implication |
| --- | --- |
| [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | Owners/bypass roles need special care; enable/force policies and test role behavior |
| [pgvector filtering](https://github.com/pgvector/pgvector#filtering) | Approximate candidate scans with filters need recall/latency evaluation |
| [DuckDB security](https://duckdb.org/security) | Treat untrusted SQL as execution requiring OS isolation |
| [DuckDB security configuration](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview) | File/network/extension capabilities require restriction; settings alone are insufficient |
| [Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html) | Idempotency, acknowledgements, worker-loss handling and retries must be designed together |
| [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpoints retain graph state; persistent state needs application access and retention controls |
| [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html) | Authentication identity is distinct from application authorization |
| [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) | Retrieved content can contain indirect instructions; structural controls limit impact |
| [S3 presigned uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html) | Reusing a key can replace content; bind processing to verified immutable identity |
| [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/) | Instrument correlated traces, metrics and logs with controlled content |
| [C4 diagrams](https://c4model.com/diagrams) | Keep context, container and component abstractions distinct |
| [PyMuPDF page API](https://pymupdf.readthedocs.io/en/latest/page.html) | Page text blocks and OCR fallback need explicit locator/quality tests |
| [pgvector index guide](https://github.com/pgvector/pgvector#hnsw) | HNSW trades build/RAM for approximate query latency and recall |
| [AWS S3 put_object](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html) | Private object writes need bucket/IAM/KMS and scoped keys |
| [openpyxl tutorial](https://openpyxl.readthedocs.io/en/stable/tutorial.html) | Read-only worksheet traversal differs from analytical type semantics |

No source claims this particular system is compliant, secure, production-ready or capable of meeting the proposed workload. Those need implementation, review and evidence.
