# ADR 008: Documents and model output are untrusted

Status: Proposed

## Context

Authorized content can contain malicious instructions, and models can emit unsupported claims or unsafe tool arguments.

## Decision

Treat content as evidence only. Tools use server-owned capability and authorization checks, typed arguments, restricted egress and budgets. Validate citations, analytical values and presentation specs; buffer sensitive answers until final checks.

## Alternatives

Prompt-only safety is insufficient. Broad autonomous agents enlarge impact without a launch requirement. Generated executable chart/Python code is rejected.

## Consequences

Some requests clarify or abstain. Schema validity does not prove semantic truth; held-out evaluation and source review remain necessary.

## Validation

Use indirect-injection, forged citation, unsafe tool, chart callback, export formula and revoked-content fixtures.

## Revisit

New tools require separate capability review and tests before exposure to orchestration.
