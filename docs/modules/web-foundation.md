# Web application foundation

Phase 2 implementation. This is an initial Next.js application, not the enterprise workspace/chat/dashboard feature set. It displays the platform model and links to real backend operational endpoints without claiming they are connected or healthy.

## WHAT and WHY

Next.js App Router renders the initial page and supplies the future web/session boundary. React supplies component composition; TypeScript checks contracts before runtime. Tailwind's PostCSS integration establishes the preferred styling toolchain, while ordinary CSS expresses this small page without introducing a component library. A plain React SPA is viable, but the approved architecture anticipates a server-side session boundary; a static export would constrain that future.

The page is deliberately useful before tenant features exist: it explains planned capabilities, identifies the current foundation release, and provides liveness/readiness/OpenAPI links. There are no fake tenant identities, uploaded documents, metrics, or successful connection indicators. Uploading later will index and retrieve data, not train the language model.

## HOW and important files

| File | Responsibility |
| --- | --- |
| `package.json` at repository root | Private npm workspace; delegates frontend checks/start/build and existing documentation checks |
| `package-lock.json` | Exact resolved dependency graph and integrity values; `npm ci` enforces consistency |
| `.npmrc` | Save exact requested dependency versions and enable audit |
| `apps/web/package.json` | Frontend scripts and explicit runtime/development dependency versions |
| `apps/web/src/app/layout.tsx` | Required root HTML/body, shared CSS, metadata and no-index search policy |
| `apps/web/src/app/page.tsx` | Server-rendered foundation page with real endpoint links and planned capability labels |
| `apps/web/src/app/globals.css` | Responsive layout, focus/skip-link affordances, reduced-motion handling and visual styling |
| `apps/web/src/lib/api-links.ts` | Validates the public API origin; rejects credentials, unsafe schemes, paths, queries and fragments |
| `apps/web/next.config.ts` | Standalone output, monorepo tracing root, strict React checks and no framework-identifying header |
| `apps/web/tsconfig.json` | Strict TypeScript and Next plugin/type generation settings |
| `apps/web/next-env.d.ts` | Next-managed framework type declarations |
| `apps/web/postcss.config.mjs` | Tailwind PostCSS pipeline |
| `apps/web/eslint.config.mjs` | ESLint CLI with Next core-web-vitals/TypeScript rules; generated outputs excluded |
| `apps/web/.prettierrc.json` / `.prettierignore` | Consistent source formatting without generated files |
| `apps/web/tests/api-links.test.mjs` | Tests the public origin trust boundary using Node's built-in runner |
| `apps/web/Dockerfile` | Locked dependency stage, build stage, then non-root standalone runtime |

`getApiOrigin(): string` reads `NEXT_PUBLIC_API_BASE_URL` or defaults to `http://localhost:8000`. A WHATWG URL parser normalizes it; explicit guards restrict it to an HTTP(S) origin without credentials or extra URL components. Errors omit the actual configuration value, which could contain an accidentally pasted secret. Output is an origin used only to construct links, not a backend fetch or secret transport.

Example accepted input: `https://api.example.test:8443/` -> `https://api.example.test:8443`. Example rejected input: a credential-bearing URL, `javascript:` URL, or `/docs` path instead of an origin. A malformed value fails the build/page render rather than creating unsafe links. Connectivity is intentionally not inferred from URL validity.

The page/layout are server components. They require no client state or browser fetch, so a backend outage does not prevent the foundation page loading. Clicking liveness (`/health/live`), readiness (`/health/ready`) or API documentation (`/docs`) reaches the separately running backend. Its documentation may be disabled outside development/test environments; that is a backend policy, not a frontend connectivity failure.

## Dependencies and runtime processes

Runtime: Next, React, React DOM. Tooling: TypeScript, matching React/Node declarations, ESLint plus Next rules, Prettier, Tailwind and its PostCSS adapter. No chart, auth, RAG, icon, state-management or API-client library is added before its feature needs one. Node's test/assert modules avoid a test-runner dependency for the small configuration boundary.

Use Node 24 (the workspace engine is `>=24 <25`). `next dev` runs development compilation/hot reload; `next build` creates optimized output; `next start` serves a completed local production build. Local dev/start scripts bind host loopback only. The standalone Docker runtime runs the generated `apps/web/server.js`, not `next dev`. It binds `0.0.0.0` inside the container, copies traced runtime modules and static assets, exposes port 3000, and runs UID 1001.

## Exact local commands

Run from the repository root:

```powershell
npm ci
npm run dev:web
```

Visit `http://localhost:3000`. The default browser API origin is `http://localhost:8000`. To override it for development, set the environment before starting Next:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = "https://api.example.test"
npm run dev:web
```

Checks and optimized execution:

```powershell
npm run lint:web
npm run typecheck:web
npm run format:check:web
npm run test:web
npm run build:web
npm run start:web
npm audit --audit-level=high
```

Run `npm run format:web` to apply formatting. Formatting checks are frontend-scoped and do not rewrite Phase 1 documents or Python files. Tests cover default origin, normalized permitted origin, and unsafe/malformed configuration denial; they do not pretend to verify future product flows.

## Configuration and container networking

`NEXT_PUBLIC_` values are public browser/build configuration. **Never put credentials in them.** Next inlines these values at build time; changing the container runtime environment does not rewrite a built page. Compose therefore supplies `NEXT_PUBLIC_API_BASE_URL` as a Docker build argument. Rebuild when changing the browser-facing API origin.

The browser must use an externally reachable origin such as `http://localhost:8000`, not a Compose service hostname like `api`. Compose DNS names resolve between containers, while the user's browser runs outside that network. Next's server is bound to `0.0.0.0` inside its container; Compose should publish port 3000 on host loopback for local development.

Docker build from repository root:

```powershell
docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 -t insightrag-web:local .
docker run --rm -p 127.0.0.1:3000:3000 insightrag-web:local
```

Use the complete Compose instructions for backend/database/worker services. This frontend Dockerfile does not provide authentication, TLS termination, or a production hosting policy.

## PRODUCTION, failures and verification

Actual executed checks will be recorded in the Phase 2 verification record. A successful compiler/build does not prove browser accessibility or Docker execution. A page's endpoint links can return connection errors while the API is stopped; that is expected and is not shown as a green status.

Actual frontend checks on 2026-11-16 with Node 24.4.1/npm 10.9.1: clean `npm ci` passed (362 packages installed, 370 audited, zero known vulnerabilities); ESLint with zero warnings, strict TypeScript, Prettier, all three configuration tests, and optimized `next build` passed. A temporary optimized server returned HTTP 200 for the page and emitted CSS, with the expected public API links; the smoke process was stopped afterward. Full visual browser/accessibility review and Docker image execution have not been performed. A local preview holding native modules open initially blocked clean installation on Windows; stop project dev servers before rerunning `npm ci`. Only verified workspace Next/PostCSS processes were stopped during verification; unrelated Node processes were not stopped.

Lockfile reproducibility is checked with `npm ci`; vulnerability auditing uses the current registry advisory feed, not a permanent assertion of safety. Image patches and supported Node/framework versions need routine maintenance. The root dependencies use exact versions after resolution. No API secret is shipped in this page.

The initial advisory scan identified a moderate minimatch glob-pattern amplification issue in the development lint dependency chain. The root `overrides` scopes patched `minimatch` 11.0.1 to `@typescript-eslint/typescript-estree`; this avoids blindly forcing an unrelated framework downgrade. Lint/type/build checks validate compatibility, and the fresh dependency installation reported zero known vulnerabilities on 2026-11-16. Revisit/remove this override when upstream resolves its range. See the [reviewed advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249).

Scale the web runtime independently from API/worker pools; avoid expensive server rendering or unbounded future dashboard fan-out. Add secure sessions, CSRF protection, content security policy and protected workspace routes in their assigned phases. An initial page with no private data is not an authorization system.

## INTERVIEW

1. **System design: how does the browser talk to services in Compose?** The browser uses host-published URLs; container service DNS names work only inside the Compose network. A later same-origin session boundary can proxy authenticated requests without exposing provider credentials.
2. **Debugging: changing `NEXT_PUBLIC_API_BASE_URL` on a running production container has no effect. Why?** Next inlines public values when building. Pass the intended browser origin at build time and rebuild, or deliberately design a separate runtime-configuration mechanism.
3. **Why server components for this page?** Static foundation information and endpoint links need no browser state. Server rendering keeps the client surface small. Future interactive workflows can introduce client components at their actual interaction boundaries.
4. **Why run lint/types/format/tests separately from build?** Each catches a different failure class; modern Next builds do not substitute for an explicit ESLint gate. Configuration tests exercise unsafe inputs while the compiler checks static contracts.
5. **What does standalone output accomplish?** Next traces required runtime files to produce a smaller deployment. The Dockerfile must still copy static assets and honor monorepo paths; it does not prove container security or production readiness by itself.

## IMPROVEMENT

Add browser journey tests when real interactions exist, a generated typed API client when domain endpoints exist, and shared design components when repetition appears. Authentication and tenancy precede private-data UI. Keep planned capability cards explicitly planned; do not replace them with invented sales numbers to make the skeleton look finished.

Primary references: [Next installation](https://nextjs.org/docs/app/getting-started/installation), [standalone output](https://nextjs.org/docs/app/api-reference/config/next-config-js/output), [deployment](https://nextjs.org/docs/app/getting-started/deploying), [environment variables](https://nextjs.org/docs/app/guides/environment-variables).
