# Module teaching guide

These are proposed module boundaries, not existing application files/classes. The WHAT/WHY/HOW/IMPLEMENTATION/PRODUCTION/IMPROVEMENT sections explain the design; [interview preparation](../interview/phase-01.md) supplies five questions with answers per domain, including system design and debugging.

| Module | Core responsibility | Companion documents |
| --- | --- | --- |
| [Identity](identity.md) | Identity, policy and tenant context | Authorization and logical schema |
| [Ingestion](ingestion.md) | Safe versioned processing and publication | Data flows, jobs ADR |
| [Retrieval](retrieval.md) | Authorized hybrid evidence selection | Retrieval concepts, vector ADR |
| [Analytics](analytics.md) | Metric plans and deterministic execution | Metric concepts, typed-plan ADR |
| [Orchestration](orchestration.md) | Bounded query workflow and answer contract | API boundaries and evidence model |
| [Visualization](visualization.md) | Typed chart/dashboard/report artifacts | Derived-artifact ADR |
| [Infrastructure](infrastructure.md) | Runtime, observability and recovery | Capacity, operations and evolution ADR |

When implementation starts, each module document must add actual file paths, important function signatures, return/error types, input/output examples and non-obvious line explanations. Do not invent code that does not exist to satisfy a teaching checklist.
