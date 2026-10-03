import { Badge, Empty, HBars, RelativeTime, Section, Sparkline, StackedBars } from "../components/ui.jsx";
import { hrefFor } from "../router.js";
import { useApp } from "../store.jsx";

export default function Telemetry() {
  const { t, metrics, health } = useApp();
  if (!metrics) return <p className="muted">{t("Loading")}…</p>;
  const latency = metrics.latency_ms || {};
  const totals = metrics.totals || {};
  const split = metrics.backend_split || {};
  const splitTotal = Object.values(split).reduce((acc, value) => acc + value, 0) || 1;
  const tests = metrics.tests_last_run || health?.tests_last_run;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Telemetry")}</h1>
          <p className="lead">{t("In-memory ring buffer of the last {n} decisions. Latency is measured inside the gateway, not the model.", { n: metrics.ring_size })}</p>
        </div>
      </div>

      <div className="cards">
        <div className="card">
          <div className="card-label">{t("Latency p50")}</div>
          <b>{latency.p50} ms</b>
          <div className="muted small">{t("avg")} {latency.avg} ms</div>
        </div>
        <div className={`card ${latency.p95 > 500 ? "warn" : ""}`}>
          <div className="card-label">{t("Latency p95")}</div>
          <b>{latency.p95} ms</b>
          <div className="muted small">{latency.samples} {t("samples")}</div>
        </div>
        <div className="card">
          <div className="card-label">{t("Requests per minute")}</div>
          <b>{metrics.rpm}</b>
          <Sparkline points={metrics.last_15_min || []} />
        </div>
        <div className="card">
          <div className="card-label">{t("Uptime")}</div>
          <b>{Math.floor((metrics.uptime_s || 0) / 60)} min</b>
          <div className="muted small">{health?.version}</div>
        </div>
        <div className={`card ${totals.upstream_errors ? "warn" : ""}`}>
          <div className="card-label">{t("Upstream errors")}</div>
          <b>{totals.upstream_errors || 0}</b>
          <div className="muted small">{t("timeouts")}: {totals.upstream_timeouts || 0}</div>
        </div>
        <div className={`card ${tests ? (tests.failed ? "critical" : "ok") : ""}`}>
          <div className="card-label">{t("Tests")}</div>
          <b>{tests ? `${tests.passed}/${tests.passed + tests.failed}` : "—"}</b>
          <div className="muted small">{tests?.ts ? <RelativeTime value={tests.ts} /> : t("run pytest to populate")}</div>
        </div>
      </div>

      <div className="grid-2">
        <Section title={t("Decisions per hour (24h)")}>
          <StackedBars rows={metrics.hourly || []} keys={["block", "redact", "allow"]} labels={{ block: t("Blocked"), redact: t("Redacted"), allow: t("Allowed") }} />
        </Section>
        <Section title={t("Backend split")}>
          {!Object.keys(split).length && <Empty />}
          <HBars rows={Object.entries(split).map(([key, value]) => ({ label: key, count: value }))} labelKey="label" />
          <p className="muted small">
            {Object.entries(split).map(([key, value]) => (
              <span key={key} className="mr">
                <Badge tone={key === "laya" ? "ok" : "warn"}>{key}</Badge> {Math.round((100 * value) / splitTotal)}%
              </span>
            ))}
          </p>
        </Section>
      </div>

      <div className="grid-3">
        <Section title={t("By kind")}>
          <HBars rows={metrics.per_kind || []} labelKey="kind" />
        </Section>
        <Section title={t("Blocks by guard")}>
          <table className="compact">
            <tbody>
              {[
                ["pii / attack", totals.block],
                [t("Attacks"), totals.attacks],
                [t("Budget"), totals.budget_blocks],
                [t("Rate limit"), totals.rate_limited],
                [t("Model allow-list"), totals.model_blocks],
                [t("Loop guard"), totals.loop_blocks],
                [t("Memory isolation"), totals.memory_blocks],
                [t("Tool allow-list"), totals.tool_blocks],
                [t("Output redactions"), totals.output_redactions],
              ].map(([label, value]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td>
                    <b>{value || 0}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
        <Section title={t("Recent decisions")}>
          <ul className="plain small">
            {(metrics.recent || []).slice(0, 15).map((event, index) => (
              <li key={index} className="row">
                <Badge tone={event.action}>{t(event.action)}</Badge>
                <span className="muted">
                  <RelativeTime value={event.ts} />
                </span>
                <span>{event.destination}</span>
                <span className="muted">{event.latency_ms} ms</span>
                {event.incident_id && (
                  <a className="link" href={hrefFor("incidents", { id: event.incident_id })}>
                    →
                  </a>
                )}
              </li>
            ))}
            {!metrics.recent?.length && <Empty />}
          </ul>
        </Section>
      </div>
    </div>
  );
}
