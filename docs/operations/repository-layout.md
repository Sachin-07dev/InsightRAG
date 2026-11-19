# Repository layout and housekeeping

Scope: Phase 2 housekeeping before owner review. No application boundary, tenant route, security policy or proposed ADR changes. The existing monorepo already separates the two applications, infrastructure, tooling and required documentation; generated local files caused most of the visual clutter.

## Source folders and request flow

```text
apps/
|-- api/
|   |-- src/insightrag/
|   |   |-- api/           # Health probes, contracts and versioned routes
|   |   |-- core/          # Configuration, safe errors, logging and middleware
|   |   |-- db/            # Database pool and request sessions
|   |   |-- main.py        # FastAPI application and resource lifecycle
|   |   `-- worker.py      # Celery configuration and diagnostic task
|   |-- migrations/       # Alembic schema history
|   `-- tests/            # Backend contracts and integration checks
`-- web/
    |-- src/
    |   |-- app/           # Next.js layout, page and global CSS
    |   `-- lib/           # Shared web helpers
    `-- tests/             # Frontend helper checks
```

The web page links to FastAPI operational endpoints. API lifecycle code owns database and Redis clients; migrations run separately with owner credentials. The worker shares the backend package without needing another placeholder application folder. See [Phase 2](../phase-02.md) for the service diagram and [local operations](phase-02-local.md) for startup.

`apps/web/src/app/layout.tsx` is the Next.js root layout: it supplies the shared HTML/body shell and metadata. `page.tsx` supplies the home page, `globals.css` the styles, and `src/lib` reusable logic. The root layout was already formatted correctly. Moving it out of the App Router directory would break Next.js conventions. Additional component or feature folders should appear when real features require them.

Root `package.json` and `package-lock.json` describe the npm workspace; root `pyproject.toml` and `uv.lock` describe the Python workspace. Keeping both locks preserves reproducible installation. Moving them into an arbitrary configuration folder would require changing package tooling, Docker builds and CI without improving the application structure.

## Required documentation

| Folder or file | Responsibility |
| --- | --- |
| `architecture/` and `architecture/decisions/` | Designs, tradeoffs and proposed ADRs |
| `concepts/` | Technical explanations and learning |
| `modules/` | Implemented and planned module responsibilities |
| `api/` | Contract boundaries and generated development OpenAPI |
| `security/` | Authorization, threats and data governance |
| `operations/` | Local execution, CI, recovery and housekeeping |
| `testing/` | Acceptance plans, manifest and actual verification records |
| `interview/` and `learning-journal.md` | Questions, model answers and owner learning |

These are required by the [standing instructions](../project-instructions.md). Historical Phase 1 documents remain useful design evidence; their existence does not mean those modules have been implemented. Existing paths also participate in the documentation manifest and links. Removing or merging them solely to shorten the tree would lose that context.

## Generated files versus persistent local state

| Path | Treatment and reason |
| --- | --- |
| `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, application `__pycache__/` | Disposable tool/bytecode caches; removed during this cleanup. Checks may recreate them. |
| `node_modules/`, `.venv/` | Installed dependencies; retained so development keeps working. Recreate deliberately with `npm ci` or `uv sync --locked --all-packages`. |
| `apps/web/.next/`, `next-env.d.ts`, `*.tsbuildinfo` | Generated web build/types; retained and hidden. Next.js dev/build recreates them; removing them may require regenerating types before checking TypeScript or starting the built app. |
| `.secrets/` | Local credentials; retained. Existing database volumes depend on consistent credentials. |
| `work/python/` | Installed Python interpreters; retained. This machine's `.venv/pyvenv.cfg` points here. |
| `work/pg-phase2/` | PostgreSQL data-directory files from earlier setup; retained. Database files require explicit lifecycle handling, even if an earlier initialization attempt failed. |
| `work/npm-cache/`, `work/uv-cache/` | Local package-manager caches; retained to avoid unnecessary downloads. |
| Four reviewed files in `work/` | Old smoke log/script, offline migration SQL and audit requirements export; removed. These are generated scratch outputs, not source or verification records. |

[Workspace settings](../../.vscode/settings.json) hide dependencies, generated output, caches, local secrets and scratch work from the VS Code Explorer. VS Code search inherits `files.exclude` by default. This only changes presentation: terminals and other tools still see the files. Edit the relevant exclusion to reveal a hidden folder. Hiding is not a security boundary; Git/Docker ignore rules and filesystem permissions still matter.

Cleanup uses explicit paths inside the verified repository root, refuses reparse-point targets, and does not use a blanket delete of ignored files. In particular, `git clean -fdx` would also remove credentials, dependencies, interpreter installations and database files here.

## Verification, failures and production limits

Run `npm run check:docs`, `node --test scripts/*.test.mjs`, and the existing web format/lint/type/test commands from the repository root. Consult [actual results](../testing/phase-02-verification.md) rather than treating this guide as a test result. Folder cleanup does not prove service integration or production readiness. No application logic changed, so it does not require a new application behavior test.

If a disposable cache is locked, leave it in place until its owning development process stops; do not stop unrelated processes to force deletion. If dependencies are removed deliberately, reinstall from locks. If the interpreter under `work/python/` is moved, recreate the virtual environment against the new interpreter rather than moving a live environment. Existing PostgreSQL/Redis services may occupy the Compose ports; follow the [Windows guide](docker-windows.md) before starting containers.

Explorer exclusions reduce visual noise; they do not change application performance. Cache removal can make the next check slower. Keep the current structure until real features justify a new module, shared package or infrastructure boundary. No Kubernetes, Terraform or empty future-feature folders are needed for this cleanup.

## Interview practice

1. **Why separate `apps/api` and `apps/web`?** They have different runtimes and build/test lifecycles while sharing one repository and coordinated contracts.
2. **Why keep the Python `src` layout?** It makes installation explicit and helps prevent tests from accidentally importing an uninstalled package from the repository root.
3. **Why not delete everything ignored by Git?** Ignore rules also cover credentials, database files and interpreters; ignored does not mean disposable.
4. **Why keep dependency locks at the root?** They resolve each workspace consistently for local development, CI and container builds.
5. **How would you debug type checking after deleting `.next`?** Regenerate Next.js types with its dev/build workflow, then rerun the check; do not hand-edit generated declarations.

## Owner understanding check

1. Which folders are source, and which are generated local state?
2. Why would deleting all of `work/` break this machine's backend environment?
3. What does Docker verify that documentation and unit checks cannot establish?
