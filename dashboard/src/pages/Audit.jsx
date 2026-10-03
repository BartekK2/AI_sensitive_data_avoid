import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Banner, Empty, RelativeTime, Section, Select } from "../components/ui.jsx";
import { hrefFor } from "../router.js";
import { useApp } from "../store.jsx";

const ACTIONS = ["allow", "redact", "block", "warn", "update", "reset", "import", "reveal"];
const DIRECTIONS = ["input", "output"];

export default function Audit() {
  const { t, data, route, navigate, toast } = useApp();
  const params = route.params;
  const [result, setResult] = useState({ items: [], count: 0, path: "" });
  const [reveal, setReveal] = useState(false);
  const [loading, setLoading] = useState(false);

  const filters = {
    action: params.action || "",
    direction: params.direction || "",
    kind: params.kind || "",
    employee: params.employee || "",
    team: params.team || "",
    destination: params.destination || "",
    q: params.q || "",
    since: params.since || "",
    until: params.until || "",
    limit: params.limit || 200,
  };

  const setFilter = (key, value) => navigate("audit", { ...params, [key]: value || undefined });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setResult(await api.audit({ ...filters, reveal: reveal || undefined }));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters), reveal]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 6000);
    return () => clearInterval(timer);
  }, [load]);

  const teams = [...new Set(data.employees.map((item) => item.team).filter(Boolean))].sort();
  const kinds = [...new Set(result.items.map((row) => row.kind).filter(Boolean))].sort();

  async function toggleReveal() {
    if (!reveal) toast({ title: t("Reveal is logged in the audit trail."), tone: "warn" });
    setReveal(!reveal);
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Audit trail")}</h1>
          <p className="lead">{t("Append-only JSONL. Every decision, policy change and reveal is recorded.")}</p>
        </div>
        <div className="page-head-aside actions">
          <a className="btn ghost" href={api.auditExportUrl({ ...filters, format: "csv" })} download>
            CSV
          </a>
          <a className="btn ghost" href={api.auditExportUrl({ ...filters, format: "jsonl" })} download>
            JSONL
          </a>
          <button className={`btn ${reveal ? "danger" : "ghost"}`} onClick={toggleReveal}>
            {reveal ? t("Hide values") : t("Reveal values")}
          </button>
        </div>
      </div>

      {reveal && <Banner tone="critical">{t("Raw values are visible. This view is recorded as an audit event.")}</Banner>}

      <div className="filters">
        <input placeholder={t("Search")} value={filters.q} onChange={(event) => setFilter("q", event.target.value)} />
        <Select value={filters.action} onChange={(value) => setFilter("action", value)} placeholder={t("Action")} options={ACTIONS.map((item) => [item, t(item)])} />
        <Select value={filters.direction} onChange={(value) => setFilter("direction", value)} placeholder={t("Direction")} options={DIRECTIONS.map((item) => [item, t(item)])} />
        <Select value={filters.kind} onChange={(value) => setFilter("kind", value)} placeholder={t("Kind")} options={kinds.map((item) => [item, item])} />
        <Select value={filters.team} onChange={(value) => setFilter("team", value)} placeholder={t("Team")} options={teams.map((item) => [item, item])} />
        <Select
          value={filters.employee}
          onChange={(value) => setFilter("employee", value)}
          placeholder={t("Person")}
          options={data.employees.map((item) => [item.id, item.name])}
        />
        <input type="datetime-local" value={filters.since} onChange={(event) => setFilter("since", event.target.value)} />
        <input type="datetime-local" value={filters.until} onChange={(event) => setFilter("until", event.target.value)} />
        <Select value={String(filters.limit)} onChange={(value) => setFilter("limit", value)} options={["50", "200", "1000", "5000"].map((item) => [item, item])} />
        <span className="muted small">
          {result.count} {loading ? "…" : ""}
        </span>
      </div>

      <Section title={<span className="mono small">{result.path}</span>}>
        {!result.items.length && <Empty />}
        <table className="compact audit">
          <thead>
            <tr>
              <th>{t("Time")}</th>
              <th>{t("Action")}</th>
              <th>{t("Kind")}</th>
              <th>{t("Person")}</th>
              <th>{t("Destination")}</th>
              <th>{t("Labels")}</th>
              <th>{t("Values")}</th>
              <th>{t("Controls")}</th>
              <th>ms</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {result.items.map((row, index) => (
              <tr key={row.request_id || index} className={row.action}>
                <td className="muted small">
                  <RelativeTime value={row.ts} />
                </td>
                <td>
                  <Badge tone={row.action}>{t(row.action)}</Badge>
                  {row.direction === "output" && <Badge tone="neutral">{t("output")}</Badge>}
                </td>
                <td className="small">{row.kind}</td>
                <td className="small">
                  {row.employee_id ? (
                    <a className="link" href={hrefFor("people", { id: row.employee_id })}>
                      {row.employee_name || row.employee_id}
                    </a>
                  ) : (
                    <span className="muted">{row.actor || "—"}</span>
                  )}
                  {row.team && <span className="muted"> · {row.team}</span>}
                </td>
                <td className="small">
                  {row.destination} {row.model && <code>{row.model}</code>}
                </td>
                <td className="small">{(row.labels || []).join(", ")}</td>
                <td className="small mono">
                  {reveal && row.raw_values ? row.raw_values.join(", ") : (row.masked_values || []).join(", ")}
                  {row.change && <span className="muted">{row.change}</span>}
                  {row.patch && <span className="muted">{JSON.stringify(row.patch)}</span>}
                </td>
                <td className="small">{(row.controls_fired || []).join(", ")}</td>
                <td className="small">{row.latency_ms}</td>
                <td>
                  {row.incident_id && (
                    <a className="link small" href={hrefFor("incidents", { id: row.incident_id })}>
                      {t("Incident")}
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
