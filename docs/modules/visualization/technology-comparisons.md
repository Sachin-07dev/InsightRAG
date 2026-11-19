# Technology choices and alternatives

| Choice | Why selected | Alternative and trigger for change |
|---|---|---|
| Apache ECharts SVG | One client renderer for line/bar, tooltips, zoom, PNG/SVG export and responsive charts; React effect owns lifecycle | Plotly React has strong scientific plotting and declarative props, but would add an adapter. Reconsider if multi-axis scientific exploration or native accessibility evaluation favors it. |
| Typed backend spec | Limits chart kinds and carries provenance; browser cannot submit values | Raw ECharts options are more flexible but permit misleading axes/labels and unsafe HTML. Add a versioned schema for richer multi-series data only after Phase 6 supports it. |
| Request-local dashboard | Every open/refresh rechecks permissions and current version | Persisted dashboards require owner/ACL tables, migrations, revocation and retention. Add only when product workflow requires sharing. |
| HTML exact table | Preserves decimal strings and supports assistive technology | Pure canvas/SVG cannot be the sole accurate numeric representation; large tables would need accessible pagination. |
| REST refresh | Each filter change is a finite authorized query | SSE suits progressive status; WebSockets suit bidirectional collaboration. Neither is needed for this bounded workload. |

Official references: [ECharts renderers](https://echarts.apache.org/handbook/en/best-practices/canvas-vs-svg/), [ECharts security](https://echarts.apache.org/handbook/en/best-practices/security/), [ECharts features](https://echarts.apache.org/en/feature.html), [Plotly React](https://plotly.com/javascript/react/). Performance is workload dependent; no chart-library throughput benchmark was run for this phase.
