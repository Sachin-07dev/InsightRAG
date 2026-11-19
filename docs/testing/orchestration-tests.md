# Phase 7 tests and execution traces

Run from repository root in the locked `.venv`:

```powershell
.venv/Scripts/pytest.exe -q apps/api/tests/test_orchestration.py
.venv/Scripts/pytest.exe -q apps/api/tests -m "not integration"
.venv/Scripts/ruff.exe check apps/api/src apps/api/tests
.venv/Scripts/ruff.exe format --check apps/api/src apps/api/tests
.venv/Scripts/mypy.exe apps/api/src
npm run check:docs
```

For a real PostgreSQL authorization regression, configure the isolated synthetic service URLs as in [analytics tests](analytics-tests.md) and run `pytest -q apps/api/tests/test_rls_integration.py -m integration`. Do not run that fixture against production data.

The five parameterized traces in [test_orchestration.py](../../apps/api/tests/test_orchestration.py) record selected route, executed nodes, tool order, and final typed output. Fixture tool outputs deliberately contain a cited shipment sentence and `100.1000` INR; they prove graph transitions and synthesis, not provider answer quality or financial approval. The same file tests no source -> clarification without tools, explicit hybrid decomposition, invalid chart scope, provider 503 partial output, authorization 404 propagation, and timeout 504. The real-service [Phase 6 regression](../../apps/api/tests/test_rls_integration.py) now asserts an analytics dataset cannot be queried under a mismatched workspace selector.

Failure matrix:

| Trigger | Expected response | Evidence |
|---|---|---|
| No source or undecomposed hybrid | Clarification, no tool call | Five-trace and decomposition tests |
| Forbidden or missing dataset | Underlying `resource_not_found`; never partial | Unauthorized-tool test; real RLS/workspace fixture |
| Document provider 503/504 after analytics | Partial, analytics only | Provider-outage test |
| Analytics provider/database error | Error; no stale numerical fallback or document-only completion | Hybrid analytics-failure test |
| Graph exceeds wall clock | `orchestration_timeout` 504 | Timeout test |
| Invalid chart without dataset | Pydantic 422 | Contract validation test |

No graph-level checkpoint recovery test exists because checkpointing is intentionally disabled. No retries are configured for side-effecting Phase 5 conversation writes. Production OIDC-provider, OpenAI-compatible provider, simultaneous-load, span-export, cost-budget and UI-chart tests are not executed by these synthetic graph tests. Counts and executed commands should be updated from actual terminal runs; do not infer them from this file.

Executed locally on 2026-11-19 after the chart-node, token-cap and workspace-wide document routing changes: the focused graph file passed **14 tests**; the complete non-integration backend suite passed **269 tests** with 62 integration cases deselected. The complete real-service integration suite passed **62 tests** before the final workspace-wide document classification unit was added; that unit passed in the focused and complete non-integration runs. Ruff check and format, mypy (58 source files), locked offline dependency resolution, OpenAPI export and 11 documentation consistency checks passed. The new HTTP security assertion denied Company B's dataset and a wrong-workspace selector in its focused real-service run. These are synthetic verification results, not measured provider quality, cost or concurrency capacity.
