import { getApiOrigin } from "@/lib/api-links";
import Link from "next/link";

const capabilities = [
  {
    number: "01",
    title: "Knowledge, with evidence",
    description:
      "Find answers across private documents and follow every claim back to its source.",
    detail: "Document retrieval",
    phase: "Planned · Phase 4–5",
  },
  {
    number: "02",
    title: "Numbers you can explain",
    description:
      "Calculate business metrics with defined dates, units, and reproducible analytical results.",
    detail: "Deterministic analytics",
    phase: "Planned · Phase 6",
  },
  {
    number: "03",
    title: "A clearer business picture",
    description:
      "Turn verified results into charts, comparisons, and dashboards with traceable data.",
    detail: "Interactive intelligence",
    phase: "Planned · Phase 8",
  },
];

export default function Home() {
  const apiOrigin = getApiOrigin();

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <Link
          className="brand"
          href="/"
          aria-label="InsightRAG Enterprise home"
        >
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            Insight<span className="brand-accent">RAG</span>
            <small>ENTERPRISE</small>
          </span>
        </Link>
        <nav aria-label="Main navigation">
          <a href="#platform">Platform</a>
          <a href="#foundation">Foundation</a>
          <Link href="/dashboard">Dashboard</Link>
          <a className="header-link" href={`${apiOrigin}/docs`}>
            API reference <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </header>

      <main id="main">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <div className="eyebrow">
              <span /> INSIGHTRAG ENTERPRISE{" "}
              <span className="eyebrow-divider">/</span> PHASE 02
            </div>
            <h1 id="hero-title">
              Private knowledge.
              <br />
              Clearer <em>decisions.</em>
            </h1>
            <p className="hero-description">
              An engineering foundation for evidence-backed answers, exact
              business analytics, and intelligence your organization can trust.
            </p>
            <div className="hero-actions">
              <a className="button-primary" href={`${apiOrigin}/docs`}>
                Explore the API <span aria-hidden="true">↗</span>
              </a>
              <a className="button-text" href="#foundation">
                View the foundation <span aria-hidden="true">↓</span>
              </a>
            </div>
            <p className="scope-note">
              Foundation release. Knowledge and analytics workflows arrive in
              later phases.
            </p>
          </div>
          <div
            className="architecture-visual"
            aria-label="Planned flow: authorized sources through policy, retrieval or analytics, to evidence-backed answers"
          >
            <div className="visual-caption">
              <span className="small-label">THE PLATFORM MODEL</span>
              <span className="caption-tag">Architecture</span>
            </div>
            <div className="source-nodes">
              <span>Documents</span>
              <span>Business data</span>
            </div>
            <div className="connector vertical" aria-hidden="true" />
            <div className="policy-node">
              <span className="node-icon" aria-hidden="true">
                ◈
              </span>{" "}
              Identity &amp; permissions{" "}
              <span className="node-end" aria-hidden="true">
                ↘
              </span>
            </div>
            <div className="connector split" aria-hidden="true" />
            <div className="engine-nodes">
              <div>
                <span className="engine-index">01</span>
                <strong>Retrieval</strong>
                <small>Find relevant evidence</small>
              </div>
              <div>
                <span className="engine-index">02</span>
                <strong>Analytics</strong>
                <small>Calculate exact results</small>
              </div>
            </div>
            <div className="connector join" aria-hidden="true" />
            <div className="answer-node">
              <span className="answer-icon" aria-hidden="true">
                ✳
              </span>
              <div>
                <strong>Answers with provenance</strong>
                <small>Facts · citations · clearly labeled insights</small>
              </div>
            </div>
            <div className="visual-footer">
              <span className="footer-line" />
              Authorization at every data boundary
            </div>
          </div>
        </section>

        <section
          id="platform"
          className="platform-section"
          aria-labelledby="platform-title"
        >
          <div className="section-heading">
            <div>
              <p className="small-label">ONE PLATFORM. DISTINCT ENGINES.</p>
              <h2 id="platform-title">Built for more than a conversation.</h2>
            </div>
            <p>
              Keep document evidence and numerical computation separate. Bring
              their results together.
            </p>
          </div>
          <div className="capability-grid">
            {capabilities.map((capability) => (
              <article className="capability-card" key={capability.number}>
                <div className="card-top">
                  <span>{capability.number}</span>
                  <span className="card-category">{capability.detail}</span>
                </div>
                <h3>{capability.title}</h3>
                <p>{capability.description}</p>
                <div className="card-phase">
                  {capability.phase}
                  <span aria-hidden="true">↗</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section
          id="foundation"
          className="foundation-section"
          aria-labelledby="foundation-title"
        >
          <div className="foundation-copy">
            <p className="small-label">CURRENT RELEASE</p>
            <h2 id="foundation-title">A foundation you can inspect.</h2>
            <p>
              This release establishes application contracts, service
              configuration, database migrations, background processing, and
              automated checks. Open the endpoints to inspect the running
              backend.
            </p>
            <span className="release-badge">
              Phase 2 · Engineering foundation
            </span>
          </div>
          <div className="endpoint-list">
            <a href={`${apiOrigin}/health/live`}>
              <div>
                <span className="endpoint-method">GET</span>
                <strong>Liveness</strong>
                <small>Is the API process responding?</small>
              </div>
              <span aria-hidden="true">↗</span>
            </a>
            <a href={`${apiOrigin}/health/ready`}>
              <div>
                <span className="endpoint-method">GET</span>
                <strong>Readiness</strong>
                <small>Are required dependencies reachable?</small>
              </div>
              <span aria-hidden="true">↗</span>
            </a>
            <a href={`${apiOrigin}/docs`}>
              <div>
                <span className="endpoint-method">GET</span>
                <strong>OpenAPI reference</strong>
                <small>Explore the versioned API contracts.</small>
              </div>
              <span aria-hidden="true">↗</span>
            </a>
            <p className="endpoint-note">
              Links open your configured API. Connectivity is not checked by
              this page.
            </p>
          </div>
        </section>
      </main>
      <footer className="site-footer">
        <span>InsightRAG Enterprise</span>
        <span>Private data. Explicit evidence. Measured progress.</span>
        <span>Foundation / 0.1</span>
      </footer>
    </div>
  );
}
