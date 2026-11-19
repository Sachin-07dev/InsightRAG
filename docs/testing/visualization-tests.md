# Phase 8 verification

Commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_visualization.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check apps/api/src/insightrag/visualization apps/api/tests/test_visualization.py
.\.venv\Scripts\mypy.exe apps/api/src/insightrag/visualization
npm run test:web
npm run typecheck:web
npm run lint:web
npm run build:web
```

The synthetic backend tests cover exact string/provenance copying, chart selection, nulls, unsupported types, non-finite values, rejection of client-supplied points, the Delhi fixture reference sums, reauthorization-call path, denied-card abort and version drift. Browser unit tests cover number conversion/rejection. They do **not** prove rendered ECharts coordinates, real OAuth browser login, export file contents, mobile assistive technology or load performance. Real-service Phase 6/7 integration tests are separate and require migrated PostgreSQL/Redis/OIDC fixtures. Record outcomes only after execution. A manual authorized UI check should upload a synthetic sales dataset, open `/dashboard`, compare each table string with the corresponding Phase 6 response, resize the viewport and try both exports; this has not been performed merely by running unit tests.

Actual local results on 2026-11-19: focused Phase 8 backend **17 passed**; complete non-integration backend **286 passed, 62 deselected**. The real-service Phase 3–7 PostgreSQL/Redis integration **62 passed, 283 deselected** before the final Phase 8-only tests were added. The integration suite does not exercise a live Phase 8 dashboard endpoint. Web unit **5 passed**; Next.js production build, ESLint, Prettier and TypeScript checks passed. Ruff check/format and mypy passed; documentation consistency and its 11 validator tests passed after restoring the existing required root-document paths. The type check initially raced with a concurrent Next.js build and reported missing generated `.next` types; rerunning it after the build passed. No browser accessibility audit, chart-image export inspection, signed-in end-to-end UI test, p95 load test or server-side PDF test was executed.
