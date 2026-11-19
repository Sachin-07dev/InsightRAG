# Recovery and deployment design

Status: Proposed; no backup, deployment or drill exists yet.

## Recovery sequence

1. Declare incident, contain access, record recovery point and authorized target region.
2. Restore PostgreSQL using tested backup/WAL procedures and restricted recovery roles.
3. Restore/reconcile object versions against catalog; quarantine missing/inconsistent resources.
4. Replay the latest independently protected deletion ledger and current access revocations. If unavailable, keep content serving closed.
5. Validate published generations/snapshots. Rebuild only where required; reconstruction time must fit the RTO or retained ready generations are needed.
6. Reconcile durable jobs/outbox, fence old workers and prevent duplicate/stale publication.
7. Verify tenant isolation, representative citations, metric results and region routes.
8. Reopen gradually, monitor errors/latency, publish incident record and review evidence.

Database RPO <=5 min and regional RTO <=60 min are targets. A restore drill measures actual loss window and elapsed time; successful backup creation alone does not prove either. Cross-region disaster recovery needs approved placement and a separately tested <=4 h proposal. Deletion policy must survive ordinary rollback.

## Rollout and rollback

Expand schema, deploy compatible readers/writers, backfill, verify, then contract after the compatibility window. Runtime roles cannot perform migrations. Feature flags scope rollout to synthetic/test tenants first. Roll back application versions only when schema/contracts remain compatible. Embedding reindex uses a staged generation with an explicit pointer switch, not in-place incompatible vectors.

## Incident responsibilities

Assign incident commander, platform recovery owner, security reviewer and data validation owner before production. Run quarterly recovery exercises plus drills after major topology changes. Record object reconciliation, tombstone replay, queue replay, index readiness, access checks and measured timing. No sensitive content in incident logs unless governed separately.
