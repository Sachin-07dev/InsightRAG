# Phase 1: system design and requirements

Date: 2026-11-16, Asia/Calcutta. Status: **Proposed, pending owner review**.

Historical Phase 1 snapshot. The owner subsequently authorized Phase 2 using this architecture direction; see the [review record](architecture/review.md) and [active phase](phase-02.md). Customer-specific production policy questions remain open.

The workspace was inspected and was empty, without Git metadata or applicable ancestor/project AGENTS.md files. This phase creates design documents and dependency-free documentation validation tooling. It creates no application, integrations, migrations, or infrastructure.

## 1. Objectives and acceptance

Establish a defensible, teachable design for all fourteen requested deliverables. Every requirement must have a design location and a future acceptance gate. Assumptions must remain distinguishable from measured behavior. See the [PRD](prd.md), [review gate](architecture/review.md), and [coverage manifest](testing/phase1-manifest.json).

## 2. Architecture and flows

Read [overview](architecture/overview.md), [C4 diagrams](architecture/c4.md), [six end-to-end flows](architecture/data-flows.md), and [schema](architecture/data-model.md).

## 3. Decisions and alternatives

Read [technology selection](architecture/technology-selection.md) and the [proposed ADRs](architecture/decisions/README.md). No ADR is approved by creating its file.

## 4. File changes

The [root guide](../README.md) maps each documentation area to its purpose. New files under `docs/` contain design, not implemented controls. `AGENTS.md` persists project guidance. `scripts/validate-phase1.mjs` checks package consistency; its test file exercises broken-link, dependency, manifest, ADR, and capacity failure detection. There are no external runtime dependencies. The package has 47 Markdown documents, 11 proposed ADRs and 26 backlog tasks; actual checks are recorded in the verification report.

## 5. Reviewable steps

This phase: establish PRD; define boundaries/flows; specify permissions/schema; estimate capacity; record choices/risks; create dependent backlog; validate documents; stop for owner review. Application work follows the [backlog](backlog.md) only after review.

## 6. Concepts and explanation

Read [retrieval versus analytics](concepts/retrieval-vs-analytics.md), [metric semantics](concepts/metric-semantics.md), and the [module guide](modules/README.md). Each module has an explicit WHAT/WHY/HOW/IMPLEMENTATION/PRODUCTION/IMPROVEMENT structure. Interview sections cover the relevant design domains.

## 7. Tests

Documentation checks run now. Application unit/integration/security gates are specified in the [acceptance plan](testing/acceptance-plan.md) and are not claimed to pass.

## 8. Local execution

From the project root, with Node.js 22+:

```powershell
node scripts/validate-phase1.mjs
node --test scripts/validate-phase1.test.mjs
```

No npm install, model credentials, Python interpreter, or cloud resources are necessary for this phase. Python installation is deferred to repository setup; the discovered Windows Python alias was not executable.

## 9. Expected and actual verification

Expected validator result: no broken local links, all deliverables mapped, valid ADR structure, acyclic backlog, and consistent capacity arithmetic. Actual execution is recorded in [verification](testing/verification.md). Mermaid source checks do not claim visual rendering or full Mermaid grammar validation.

## 10. Limitations and failures

See [threats](security/threat-model.md), [risk register](architecture/assumptions-risks-decisions.md), and [governance](security/residency-retention-deletion.md). No hosted region, customer contract, metric definition, provider settings, or permission model has been owner-approved.

## 11. Performance

[Capacity and objectives](architecture/capacity-and-slos.md) state formulas and workload envelopes. They are planning estimates, not benchmarks or service promises.

## 12. Interview preparation

[Interview exercises](interview/phase-01.md) include model answers, system-design questions, and debugging scenarios across the architecture domains.

## 13. Documentation updates

All required documentation areas are established. The [learning journal](learning-journal.md) records concepts and open decisions. Review source references before pinning implementation versions.

## 14. Next-phase dependencies and stop point

Read the [approval checklist](architecture/review.md). Resolve or explicitly defer launch region, access granularity, metrics, retention, and workload envelope. Then Phase 2 may implement repository/infrastructure foundations. Do not begin it automatically.

Understanding check:

1. Why does a sales comparison need analytics even when reports mention sales?
2. Why must an existing chart be reauthorized when reopened?
3. What stops a retried worker publishing a deleted document version?
