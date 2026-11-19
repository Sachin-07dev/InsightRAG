"""Authorization, fixed SQL aggregation, policy fencing, and provenance."""
# ruff: noqa: E501

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from insightrag.analytics.contracts import (
    AnalyticsRequest,
    AnalyticsResponse,
    AnalyticsRow,
    AnalyticsSchema,
)
from insightrag.analytics.planning import (
    METRIC_DEFINITION_VERSION,
    METRICS,
    QueryPlan,
    plan_question,
)
from insightrag.db.session import Database
from insightrag.security.context import AccessContext, SecurityError, not_found
from insightrag.security.database import require_resource, tenant_session
from insightrag.security.dependencies import audit

_DIMENSIONS = {
    "total": ("'all'", ""),
    "region": ("region", "GROUP BY region"),
    "product": ("product", "GROUP BY product"),
    "month": (
        "to_char(transaction_date,'YYYY-MM')",
        "GROUP BY to_char(transaction_date,'YYYY-MM')",
    ),
}


async def _set_sales_scope(session: AsyncSession, resource_id: UUID) -> None:
    """Bind one server-authorized resource for the fact-table RLS policy."""
    await session.execute(
        text("SELECT set_config('app.analytics_resource_id', :resource, true)"),
        {"resource": str(resource_id)},
    )


async def discover(database: Database, access: AccessContext, resource_id: UUID) -> AnalyticsSchema:
    scoped = access.for_operation("analytics")
    async with tenant_session(database, scoped) as session:
        resource = await require_resource(session, scoped, resource_id, "query")
        if resource["kind"] != "dataset" or resource["state"] != "active":
            raise not_found()
        await _set_sales_scope(session, resource_id)
        row = (
            (
                await session.execute(
                    text("""SELECT r.active_version,o.reporting_timezone
            FROM resources r JOIN orgs o ON o.id=r.org_id
            WHERE r.org_id=:org AND r.id=:resource"""),
                    {"org": scoped.organization_id, "resource": resource_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["active_version"] is None:
            raise not_found()
        has_rows = await session.scalar(
            text("""SELECT EXISTS(SELECT 1 FROM analytics_sales_rows
            WHERE org_id=:org AND resource_id=:resource AND version_id=:version)"""),
            {
                "org": scoped.organization_id,
                "resource": resource_id,
                "version": row["active_version"],
            },
        )
        if not has_rows:
            raise not_found()
        await audit(session, scoped, "analytics.schema", resource_id)
        return AnalyticsSchema(
            resource_id=resource_id,
            version_id=row["active_version"],
            columns={
                "transaction_date": "date",
                "region": "text",
                "product": "text",
                "revenue": "decimal(20,4)",
                "cost": "decimal(20,4)",
                "units": "integer",
                "returns": "integer",
                "currency": "ISO-like code",
            },
            metrics={name: details[1] for name, details in METRICS.items()},
            metric_definition_version=METRIC_DEFINITION_VERSION,
            reporting_timezone=row["reporting_timezone"],
        )


def _query(plan: QueryPlan) -> str:
    """All identifier and expression fragments come from sealed server constants."""
    expression = METRICS[plan.metric][0]
    dimension, group = _DIMENSIONS[plan.breakdown]
    return (
        f"SELECT {dimension} AS dimension,{expression} AS value,COUNT(*) AS source_rows,"
        "MIN(row_number) AS source_row_min,MAX(row_number) AS source_row_max "
        "FROM analytics_sales_rows WHERE org_id=:org AND resource_id=:resource "
        "AND version_id=:version AND currency=:currency "
        "AND transaction_date>=:start AND transaction_date<:end "
        "AND (CAST(:region AS text) IS NULL OR region=:region) "
        f"{group} ORDER BY dimension LIMIT 500"
    )


def _growth_percent(current: Decimal | None, baseline: Decimal | None) -> str | None:
    """Do not assign business meaning to absent, zero, or negative baselines."""
    if current is None or baseline is None or baseline <= 0:
        return None
    return str((current - baseline) * Decimal(100) / baseline)


async def analyze(
    database: Database,
    access: AccessContext,
    request: AnalyticsRequest,
    expected_workspace_id: UUID | None = None,
) -> AnalyticsResponse:
    scoped = access.for_operation("analytics")
    async with tenant_session(database, scoped) as session:
        await session.execute(text("SET LOCAL statement_timeout = '3000ms'"))
        await session.execute(text("SET LOCAL work_mem = '8MB'"))
        resource = await require_resource(session, scoped, request.resource_id, "query")
        if resource["kind"] != "dataset" or resource["state"] != "active":
            raise not_found()
        if expected_workspace_id is not None and resource["workspace_id"] != expected_workspace_id:
            raise not_found()
        await _set_sales_scope(session, request.resource_id)
        metadata = (
            (
                await session.execute(
                    text("""SELECT r.active_version,v.version_number,v.sha256,o.reporting_timezone
                FROM resources r JOIN document_versions v ON v.org_id=r.org_id AND v.resource_id=r.id
                  AND v.id=r.active_version JOIN orgs o ON o.id=r.org_id
                WHERE r.org_id=:org AND r.id=:resource"""),
                    {"org": scoped.organization_id, "resource": request.resource_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if metadata is None:
            raise not_found()
        timezone = metadata["reporting_timezone"]
        try:
            today = datetime.now(ZoneInfo(timezone)).date()
            plan = plan_question(request, today, timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise SecurityError(422, "analytics_clarification_required", str(exc)) from None
        # Schema discovery sees only entitled rows; unsupported/empty projections fail closed.
        currencies = (
            (
                await session.execute(
                    text("""SELECT DISTINCT currency FROM analytics_sales_rows
            WHERE org_id=:org AND resource_id=:resource AND version_id=:version LIMIT 2"""),
                    {
                        "org": scoped.organization_id,
                        "resource": request.resource_id,
                        "version": metadata["active_version"],
                    },
                )
            )
            .scalars()
            .all()
        )
        if not currencies:
            raise SecurityError(
                422, "analytics_schema_unavailable", "No authorized governed sales rows"
            )
        currency = request.currency
        if currency is None:
            if len(currencies) != 1:
                raise SecurityError(422, "analytics_clarification_required", "Specify a currency")
            currency = currencies[0].strip()
        if currency not in [item.strip() for item in currencies]:
            raise not_found()
        if plan.metric == "contribution":
            complete = await session.scalar(
                text("SELECT insightrag_security.has_complete_sales_scope(:org,:resource)"),
                {"org": scoped.organization_id, "resource": request.resource_id},
            )
            if not complete:
                raise SecurityError(
                    422,
                    "analytics_scope_incomplete",
                    "National contribution requires access to every dataset region",
                )
        params = {
            "org": scoped.organization_id,
            "resource": request.resource_id,
            "version": metadata["active_version"],
            "currency": currency,
            "region": request.region,
            "start": plan.start,
            "end": plan.end,
        }
        rows = (await session.execute(text(_query(plan)), params)).mappings().all()
        denominator: Decimal | None = None
        if plan.metric == "contribution":
            national_rows = (
                (
                    await session.execute(
                        text(_query(replace(plan, breakdown="total"))), dict(params, region=None)
                    )
                )
                .mappings()
                .all()
            )
            denominator = national_rows[0]["value"] if national_rows else None
        previous: dict[str, Decimal | None] = {}
        if plan.comparison_start and plan.comparison_end:
            older = dict(params, start=plan.comparison_start, end=plan.comparison_end)
            previous = {
                str(row["dimension"]): row["value"]
                for row in (await session.execute(text(_query(plan)), older)).mappings()
            }
        if not any(row["source_rows"] for row in rows) and not any(
            value is not None for value in previous.values()
        ):
            raise SecurityError(422, "analytics_no_data", "No authorized rows in the period")
        revision = await session.scalar(
            text("SELECT insightrag_security.lock_member_policy_revision(:org)"),
            {"org": scoped.organization_id},
        )
        if revision != scoped.policy_revision:
            raise SecurityError(409, "authorization_changed", "Authorization changed; retry")
        await require_resource(session, scoped, request.resource_id, "query")
        if (
            await session.scalar(
                text("SELECT active_version FROM resources WHERE org_id=:org AND id=:resource"),
                {"org": scoped.organization_id, "resource": request.resource_id},
            )
            != metadata["active_version"]
        ):
            raise SecurityError(409, "dataset_changed", "Dataset version changed; retry")
        await audit(session, scoped, "analytics.query", request.resource_id)
    output: list[AnalyticsRow] = []
    for row in rows:
        value = row["value"]
        comparison = previous.get(str(row["dimension"]))
        if row["source_rows"] == 0 and comparison is not None:
            value = Decimal(0)
        if plan.metric == "contribution":
            value = (
                value * Decimal(100) / denominator if value is not None and denominator else None
            )
        growth = _growth_percent(value, comparison)
        output.append(
            AnalyticsRow(
                dimension=str(row["dimension"]),
                value=str(value) if value is not None else None,
                comparison_value=str(comparison) if comparison is not None else None,
                growth_percent=growth,
                source_rows=row["source_rows"],
                source_row_min=row["source_row_min"],
                source_row_max=row["source_row_max"],
            )
        )
    if plan.comparison_start is not None:
        current_dimensions = {item.dimension for item in output}
        for dimension, baseline in previous.items():
            if dimension not in current_dimensions:
                output.append(
                    AnalyticsRow(
                        dimension=dimension,
                        value="0",
                        source_rows=0,
                        comparison_value=str(baseline) if baseline is not None else None,
                        growth_percent=_growth_percent(Decimal(0), baseline),
                    )
                )
        if "highest" in request.question.casefold():
            output.sort(
                key=lambda item: (
                    item.growth_percent is None,
                    -Decimal(item.growth_percent) if item.growth_percent is not None else 0,
                    item.dimension,
                )
            )
    return AnalyticsResponse(
        metric=plan.metric,
        definition=METRICS[plan.metric][1],
        metric_definition_version=METRIC_DEFINITION_VERSION,
        unit="percent"
        if plan.metric in ("margin", "contribution")
        else currency
        if METRICS[plan.metric][2] == "currency"
        else "units",
        reporting_timezone=timezone,
        period_start=plan.start.isoformat(),
        period_end_exclusive=plan.end.isoformat(),
        filters={"currency": currency, **({"region": request.region} if request.region else {})},
        resource_id=request.resource_id,
        version_id=metadata["active_version"],
        version_number=metadata["version_number"],
        source_sha256=metadata["sha256"],
        rows=output,
        notes=[
            "Only currently authorized rows are included.",
            "Growth is null when the comparison baseline is absent, zero, or negative.",
        ],
    )
