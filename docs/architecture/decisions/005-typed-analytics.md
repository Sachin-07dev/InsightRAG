# ADR 005: Typed analytical plans and isolated execution

Status: Proposed

## Context

Generated SQL can expose data, access engine capabilities or exhaust resources even when described as read-only.

## Decision

Compile validated metric plans into controlled SQL. Run DuckDB with authorized snapshots in restricted disposable processes; connectors use approved objects and read-only credentials. Enforce CPU/memory/time/temp-disk/scan/result limits.

## Alternatives

Raw model SQL plus AST checks offers flexibility but a larger security surface. Unrestricted generated Python is rejected. Warehouses suit larger concurrent data but still need semantic/access controls.

## Consequences

Supported analysis is intentionally bounded. SQL validation is not a sandbox; no host secrets/network/unrelated tenant files reach the executor.

## Validation

Golden calculations plus file/network/extension/unauthorized-object and resource-exhaustion tests.

## Revisit

Expand plan vocabulary under review. Arbitrary SQL requires a new decision, not a silent adapter change.
