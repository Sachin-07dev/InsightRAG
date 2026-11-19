# Metric semantics and deterministic business analysis

Status: Business definitions are examples awaiting approval, not customer financial policy.

## What a metric definition contains

Name, owner, immutable version, expression, data grain, allowed joins/dimensions, inclusion/exclusion rules, unit, currency conversion, null handling, date attribution, timezone, reporting calendar and rounding policy. SQL can be arithmetically correct while answering the wrong definition.

For net sales, ask whether discounts, returns, tax, shipping, cancelled orders and exchange-rate adjustments apply. Prevent join fan-out: joining one order to many lines and many refunds can multiply amounts unless preaggregated at the proper grain.

## Time and comparison semantics

As of 16 November 2026, previous three complete calendar months are August, September and October in the organization's reporting timezone. Use [2026-08-01, 2026-11-01), converting to UTC instants when source timestamps require it. Do not assume Asia/Calcutta for every customer merely because it is the owner's timezone.

Growth = (current - prior) / prior. Prior zero -> undefined with explanation, not infinity. Missing period is not automatically zero. A zero numerator with a nonzero prior is valid. Percentage-point change differs from percent change; identify which is requested. Fiscal calendars need an approved calendar table/version.

## Numerical integrity

Use decimal types for currency; retain source currency and normalized currency separately. Never sum mixed currencies silently. Rounding occurs at approved points; display rounding is not source-value mutation. Dataset profiling identifies ambiguous date formats, duplicate keys, unexpected nulls and cached spreadsheet formulas. Formula cells are not executed by the platform.

## Evidence and reproducibility

Record metric version, dataset snapshot, typed plan/hash, bound filters, date interval, timezone, execution time, units and freshness. A live connector without a retained snapshot may not reproduce historical results; label that weaker contract rather than asserting exact replay.

Example: two synthetic rows, INR 100.10 and INR 200.20, total INR 300.30 under the declared metric. A chart and narrative both use that returned result; the model never recomputes it. Golden tests expand to refunds, joins, leap days, DST, nulls and zero denominators.
