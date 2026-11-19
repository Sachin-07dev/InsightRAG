# InsightRAG Enterprise project instructions

Read [the standing master instructions](docs/project-instructions.md) and [the current phase guide](docs/phase-06.md) before making significant changes. These persist the user's Master Prompt 0. User instructions in chat take precedence.

- Inspect existing files and nested instructions before editing. Preserve working implementations unless a replacement is explained.
- Work in one bounded phase. Present significant design changes before implementing; stop at each major phase for review. The owner explicitly authorized Phase 6 analytics. Do not begin Phase 7 or later phases automatically.
- Enforce organization, workspace, and resource permissions before retrieval, analytics, source downloads, and derived-artifact access. Fail closed.
- Separate document retrieval from deterministic numerical analytics. Never claim ingestion trains the LLM.
- Treat document content and model output as untrusted. No unrestricted generated SQL or Python. Tools require validated contracts and resource limits.
- Preserve source versions, real locators, metric semantics, units, reporting timezone, and date boundaries. Never invent evidence, citations, integrations, or values.
- Jobs must tolerate duplication, retries, partial failure, cancellation, updates, and deletion. Use version fencing and idempotent effects.
- No hardcoded secrets or production tenant identities. Use synthetic examples.
- Maintain the documentation areas required by the master prompt, including ADRs, concepts, modules, security, operations, testing, interview preparation, and the learning journal.
- Teach WHAT, WHY, HOW, IMPLEMENTATION, PRODUCTION, INTERVIEW, and IMPROVEMENT for significant work. Explain important files, non-obvious code, alternatives, error behavior, and operational tradeoffs.
- Run appropriate available checks. Report actual results and distinguish document validation, prototype behavior, and production assurance.
- Keep assumptions, risks, and deferred decisions explicit. Do not mark proposed ADRs approved without owner review.
- End each implementation phase with three conceptual questions.
