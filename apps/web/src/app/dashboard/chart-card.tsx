"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { toFiniteNumbers, type DashboardResponse } from "@/lib/visualization";

type Card = DashboardResponse["cards"][number];

export default function ChartCard({ card }: { card: Card }) {
  const node = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const { view } = card;
  useEffect(() => {
    if (!node.current || !["line", "bar"].includes(view.kind)) return;
    let instance: echarts.ECharts;
    try {
      instance = echarts.init(node.current, undefined, { renderer: "svg" });
      chart.current = instance;
      instance.setOption({
        animation: false,
        aria: { enabled: true },
        title: {
          text: `${view.metric} (${view.unit})`,
          subtext: `Dataset ${view.source.resource_id} v${view.source.version_number} · ${view.period_start} to ${view.period_end_exclusive}`,
          textStyle: { fontSize: 14 },
          subtextStyle: { fontSize: 10 },
        },
        tooltip: { trigger: "axis", renderMode: "richText" },
        legend: { show: false },
        grid: { containLabel: true, left: 12, right: 12, top: 70, bottom: 45 },
        dataZoom:
          view.points.length > 12
            ? [{ type: "inside" }, { type: "slider" }]
            : [],
        xAxis: {
          type: "category",
          data: view.points.map((p) => p.label),
          name: view.kind === "line" ? "Month" : "Dimension",
        },
        yAxis: {
          type: "value",
          name: view.unit,
          min: view.points.every(
            (p) => p.value !== null && Number(p.value) >= 0,
          )
            ? 0
            : undefined,
        },
        series: [
          {
            type: view.kind,
            name: view.metric,
            data: toFiniteNumbers(view.points),
          },
        ],
      });
    } catch {
      return;
    }
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(node.current);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, [view]);

  function exportImage(type: "png" | "svg") {
    const instance = chart.current;
    if (!instance) return;
    const url = instance.getDataURL({
      type,
      pixelRatio: 2,
      backgroundColor: "#ffffff",
    });
    const link = document.createElement("a");
    link.href = url;
    link.download = `${view.metric}-${view.source.version_id}.${type}`;
    link.click();
  }

  return (
    <article className="dashboard-card">
      <h2>{card.question}</h2>
      {view.kind === "kpi" && (
        <p className="dashboard-kpi">
          {view.points[0]?.value ?? "Undefined"} <small>{view.unit}</small>
        </p>
      )}
      {["line", "bar"].includes(view.kind) && (
        <div
          ref={node}
          className="dashboard-chart"
          role="img"
          aria-label={`${view.metric} ${view.kind} chart; exact values in table below`}
        />
      )}
      <div className="dashboard-table-wrap">
        <table>
          <caption>
            Verified {view.metric} values ({view.unit})
          </caption>
          <thead>
            <tr>
              <th scope="col">Dimension</th>
              <th scope="col">Value</th>
              <th scope="col">Source rows</th>
            </tr>
          </thead>
          <tbody>
            {view.points.map((point) => (
              <tr key={point.label}>
                <th scope="row">{point.label}</th>
                <td>{point.value ?? "Undefined"}</td>
                <td>{point.source_rows}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="dashboard-meta">
        {view.definition} · {view.period_start} to {view.period_end_exclusive}{" "}
        (end exclusive) · {view.reporting_timezone}
      </p>
      <p className="dashboard-meta">
        Filters:{" "}
        {Object.entries(view.filters)
          .map(([key, value]) => `${key}=${value}`)
          .join(", ") || "None"}
      </p>
      <p className="dashboard-meta">
        Dataset version {view.source.version_number} · metric definition{" "}
        {view.source.metric_definition_version}
      </p>
      {view.insights.map((insight) => (
        <p className="dashboard-meta" key={insight.text}>
          <strong>{insight.kind.replaceAll("_", " ")}:</strong> {insight.text}
        </p>
      ))}
      {["line", "bar"].includes(view.kind) && (
        <div className="dashboard-exports">
          <button type="button" onClick={() => exportImage("png")}>
            Export PNG
          </button>
          <button type="button" onClick={() => exportImage("svg")}>
            Export SVG
          </button>
        </div>
      )}
    </article>
  );
}
