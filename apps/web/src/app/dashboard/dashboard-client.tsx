"use client";

import { useState } from "react";
import Link from "next/link";
import type { DashboardResponse } from "@/lib/visualization";
import ChartCard from "./chart-card";

const starterViews = [
  {
    question: "Monthly revenue for Delhi in 2025",
    kind: "line",
    region: "Delhi",
    year: 2025,
  },
  {
    question: "Delhi revenue in 2025",
    kind: "kpi",
    region: "Delhi",
    year: 2025,
  },
  {
    question: "Percentage of national revenue from Delhi in 2025",
    kind: "kpi",
    region: "Delhi",
    year: 2025,
  },
  {
    question: "Revenue by product in 2025",
    kind: "bar",
    region: "Delhi",
    year: 2025,
  },
  { question: "Revenue by region in 2025", kind: "bar", year: 2025 },
  { question: "Revenue by region in 2025", kind: "table", year: 2025 },
] as const;

export default function DashboardClient() {
  const [token, setToken] = useState("");
  const [organization, setOrganization] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [dataset, setDataset] = useState("");
  const [year, setYear] = useState(2025);
  const [region, setRegion] = useState("Delhi");
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setData(null);
    try {
      const views = starterViews.map((view) => ({
        ...view,
        question: view.question
          .replaceAll("Delhi", region)
          .replaceAll("2025", String(year)),
        year,
        ...(Object.hasOwn(view, "region") ? { region } : {}),
      }));
      const response = await fetch("/api/dashboard", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "X-Organization-ID": organization,
        },
        body: JSON.stringify({
          workspace_id: workspace,
          dataset_id: dataset,
          views,
        }),
        cache: "no-store",
      });
      if (!response.ok) {
        setError(
          `Dashboard unavailable (${response.status}). Check access, dataset, and metric definitions.`,
        );
        return;
      }
      setData((await response.json()) as DashboardResponse);
    } catch {
      setError(
        "Dashboard service is unavailable. Retry after checking the connection.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <a href="#dashboard-results" className="skip-link">
        Skip to results
      </a>
      <header className="dashboard-header">
        <Link href="/" className="dashboard-brand">
          InsightRAG Enterprise
        </Link>
        <h1>Verified business dashboard</h1>
        <p>
          Every view is recalculated from an authorized dataset. Values are
          never supplied by the browser.
        </p>
      </header>
      <form onSubmit={refresh} className="dashboard-controls">
        <label>
          Access token{" "}
          <input
            type="password"
            autoComplete="off"
            required
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </label>
        <label>
          Organization ID{" "}
          <input
            required
            value={organization}
            onChange={(event) => setOrganization(event.target.value)}
          />
        </label>
        <label>
          Workspace ID{" "}
          <input
            required
            value={workspace}
            onChange={(event) => setWorkspace(event.target.value)}
          />
        </label>
        <label>
          Dataset ID{" "}
          <input
            required
            value={dataset}
            onChange={(event) => setDataset(event.target.value)}
          />
        </label>
        <label>
          Reporting year{" "}
          <input
            type="number"
            min="1900"
            max="2100"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
          />
        </label>
        <label>
          Region{" "}
          <input
            required
            value={region}
            onChange={(event) => setRegion(event.target.value)}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Verifying…" : "Refresh authorized results"}
        </button>
      </form>
      <p className="dashboard-limitation">
        Month-over-month growth and category-level breakdown remain unavailable
        until approved metric and schema contracts exist. Product breakdown is
        shown instead.
      </p>
      {error && (
        <p role="alert" className="dashboard-error">
          {error}
        </p>
      )}
      {!data && !error && !loading && (
        <p>Enter an authorized dataset and refresh to see verified results.</p>
      )}
      {data && (
        <button
          className="dashboard-print"
          type="button"
          onClick={() => window.print()}
        >
          Print current verified report
        </button>
      )}
      <section
        id="dashboard-results"
        className="dashboard-grid"
        aria-live="polite"
      >
        {data?.cards.map((card, index) => (
          <ChartCard key={`${index}-${card.question}`} card={card} />
        ))}
      </section>
    </main>
  );
}
