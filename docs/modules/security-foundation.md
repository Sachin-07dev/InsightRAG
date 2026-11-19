# Security foundation module

This bounded module owns verified identity, current permissions and security controls; it does not parse documents, generate answers, run arbitrary analytics or render charts. Its transport layer is the protected FastAPI router, its policy authority is current PostgreSQL data, and its asynchronous entry point is a signed job plus durable authorization state.

The [implementation teaching guide](../concepts/phase-03-security.md) explains each important file/class/function, request flow, data model, alternatives, non-obvious transaction/RLS behavior, operational failure modes and improvement triggers. The [phase guide](../phase-03.md) maps files and acceptance criteria. The [runbook](../operations/phase-03-security.md) documents actual operator boundaries and exact commands. The [interview guide](../interview/phase-03.md) covers design/debugging questions for every major security area.

Public module rules for later phases:

- Obtain an immutable verified AccessContext; derive a trusted purpose, never accept role/MFA/tenant authority from model output or retrieved text.
- Open a transaction-local tenant session and authorize each resource/action before obtaining content, executing fixed analytical plans or downloading derived artifacts.
- Reauthorize every source of a chart/dashboard and record lineage/version/policy revision. A dashboard workspace does not grant access to all its sources.
- Use tenant-scoped object/cache namespaces, but also enforce current authorization before returning cached/stored bytes.
- Treat job envelopes as bounded delegation; reload current durable job and policy before effects. Version fencing for ingestion/publication remains mandatory in Phase 4.
- Keep DB operator credentials, managed keys, telemetry administration and cloud storage ownership outside user-facing processes.

Tests and actual evidence are in [verification](../testing/phase-03-verification.md). Passing these cases is a prerequisite for extending the module, not proof of production compliance or unrestricted model/tool safety.
