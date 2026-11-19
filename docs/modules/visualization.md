# Visualization, dashboards and reports

## WHAT

Turns validated analytical results into interactive ECharts views, saved dashboard definitions and downloadable CSV/PDF reports.

## WHY

Charts reveal trends/comparisons better than prose when values are trustworthy. A constrained specification is inspectable and safer than arbitrary generated JavaScript. Plotly or Vega-Lite remain viable alternatives; scientific visualization needs may change the choice.

## HOW

Result schema -> allowed chart recommendation -> bind real columns -> validate units/series/sort/aggregation -> render chart and accessible table. Dashboard refresh reauthorizes source dependencies and pins the resulting versions; panels show stale/partial-error state individually. Export workers use constrained templates and recheck access at generation/download.

## IMPLEMENTATION

Proposed chart spec includes result_id, chart_type, x column, y measure columns, units and safe display labels. No callbacks, executable expressions, arbitrary HTML or external URLs. A monthly net-sales line chart takes month and INR values directly from the analytical result; no LLM interpolation. Unsupported schema or mixed-unit series is rejected or presented as a table.

## PRODUCTION

Limit point/series counts and dashboard fan-out. Any downsampling/aggregation must be explicit and retain source/result provenance. Protect against browser XSS, CSV formula injection and unsafe PDF rendering. Shared artifacts cannot widen source access. Mobile/keyboard usability and data-table alternatives are acceptance concerns, not optional polish.

## IMPROVEMENT

Add governed templates, richer filters and scheduled refresh after measuring user needs and cost. Sharing and redacted views need explicit policy design. Caches/materialized results expire on source or permission changes; old downloaded files cannot be recalled.
