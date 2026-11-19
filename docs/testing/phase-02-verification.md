# Phase 2 verification record

Date: 2026-11-16, Asia/Calcutta. Workspace: `D:\projects\RAG`. This record separates executed checks from configured future checks. No Docker or hosted-CI run is inferred.

## Executed so far

| Check | Actual result |
| --- | --- |
| Python install and locked workspace sync | Python 3.12.16, uv 0.13.7; exact lock generated and 84 packages installed |
| Ruff source checks/format | Passed final whole-repository check |
| Strict mypy | Passed, 15 source files |
| Backend unit/security-focused tests | 23 passed, 4 real-service tests deselected; one Starlette HTTPX deprecation warning |
| Real native Uvicorn HTTP smoke | Passed: liveness, unconfigured 503 readiness, metadata, OpenAPI, echo, 422 validation and request correlation; temporary process stopped |
| OpenAPI export | Generated development/test contract in docs/api/openapi.json without connecting to services |
| Offline Alembic migration | SQL generation passed; contains foundation metadata, restricted SELECT grant and expected revision |
| Secret bootstrap tests | 3 passed; real bootstrap rerun preserved credentials |
| Documentation/bootstrap Node suite | 13 passed, 0 failed |
| Design document consistency | No errors; all 14 deliverables and 21 PRD requirements remain mapped |
| Compose/CI YAML parsing | Parsed successfully using PyYAML; not Docker schema/runtime validation |
| Dependency registry metadata | Selected PostgreSQL/Redis tags and manifest digests verified; action commits pinned |
| Frontend installation | Clean npm ci succeeded; 362 installed / 370 audited, 0 reported vulnerabilities |
| Frontend checks | ESLint zero warnings, Prettier, strict TypeScript and all 3 public-origin tests passed |
| Frontend optimized build | Next.js production build passed |
| Frontend production HTTP smoke | Page and CSS asset returned successfully; temporary preview processes stopped |

## Pre-review folder cleanup, 2026-11-16

The owner requested repository housekeeping before the next phase. Source folders, workspace manifests/locks, application behavior and required documentation areas were preserved. Added shared VS Code Explorer exclusions, a README tree, the [folder guide](../operations/repository-layout.md), and [Windows Docker installation instructions](../operations/docker-windows.md).

Removed three root tool caches and eight application `__pycache__` directories, plus four reviewed scratch outputs: `work/api-smoke.log`, `work/foundation-migration.sql`, `work/requirements-audit.txt` and `work/smoke-web.mjs`. Total: 15 targets, 54 files, 18,838,366 bytes. Every final path was checked inside the repository and reparse-point targets were rejected before recursive removal. The first preflight stopped on a PowerShell parameter incompatibility before any deletion; the corrected preflight and removal completed successfully.

Preserved installed dependencies, the Python environment/interpreter, generated web build/types, `.secrets/`, package caches and PostgreSQL data-directory files in `work/pg-phase2/`. These retained local files are hidden in VS Code where appropriate, not deleted. No database process or Windows service was stopped or reconfigured.

| Check after housekeeping | Actual result |
| --- | --- |
| Documentation consistency | Passed; 56 Markdown files, all 14 deliverables/21 requirements/11 proposed ADRs retained |
| Existing Node documentation/bootstrap suite | 13 passed, 0 failed |
| Frontend format, ESLint, TypeScript | All passed; ESLint configured with zero allowed warnings |
| Existing frontend helper tests | 3 passed, 0 failed |
| Editor diagnostics for changed files | No errors reported |

Backend tests and production web build were not rerun for this documentation/settings/cache-only change; the earlier results above remain historical. No new behavioral tests were added. Documentation/editor checks do not establish Explorer rendering on every user configuration, application security or production assurance.

Docker remains absent. The detected host is 64-bit Windows 10 Pro 22H2, build 19045.7548; WSL and WinGet commands exist, but modern WSL2, hardware virtualization and current Windows/Docker support eligibility were not established. No Docker/WSL installation, reboot, container build, service integration or hosted CI run occurred during cleanup. See the Windows guide for exact steps and the support boundary.

## Not established by those checks

Docker is not installed. Compose config/build/startup, Linux image behavior, real Redis delivery, container worker round trip and complete Compose smoke have not been executed locally. CI contains these checks but has not run on a hosted repository. No throughput/load, tenant isolation, RAG quality or production readiness is claimed.

Python pip-audit initially could not use its default cache in the restricted environment; the rerun requested project-local cache and public network access. That approval was declined. **Python vulnerability scanning remains unverified locally**; the workflow contains a strict runtime scan. Do not report a clean scan or bypass the declined command via another tool.

Frontend checks establish build/configuration behavior, not full browser/accessibility acceptance. Windows clean npm installation required stopping only verified project Next/PostCSS processes holding native modules open. The scoped minimatch override resolves a lint-tool-chain advisory; the resulting installed graph reported zero npm advisories. Dependency scan results are time-specific, not proof that no vulnerabilities exist.

## Native PostgreSQL attempt

The existing PostgreSQL 18 binaries were discovered and a disposable workspace cluster setup was attempted as an alternative to Docker. `initdb` failed under the restricted Windows token (errors 87/3); an escalated retry was aborted. Setup left partial ignored work directories. No PostgreSQL startup command was issued, neither temporary directory has postmaster.pid, and no existing PostgreSQL service was modified. Therefore **real migration execution and runtime privilege integration remain unverified**, not passed. Offline SQL generation is the only executed migration check.

See [local runbook](../operations/phase-02-local.md) for setup and [CI runbook](../operations/phase-02-ci.md) for real-service/audit commands.

## Commands used for backend verification here

Ordinary installations use uv commands in the phase guide. This machine required project-local interpreter/cache paths:

```powershell
$env:UV_CACHE_DIR = 'D:\projects\RAG\work\uv-cache'
$env:UV_PYTHON_INSTALL_DIR = 'D:\projects\RAG\work\python'
uv python install 3.12
uv sync --locked --all-packages
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\mypy.exe
.venv\Scripts\python.exe -m pytest --tb=short
.venv\Scripts\python.exe scripts/smoke-api.py
```

These paths are local setup facts, not hardcoded application configuration. No service credentials are printed or committed. Work/.venv/.secrets are ignored.
