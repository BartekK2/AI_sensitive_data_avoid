import { useState } from "react";
import { api } from "../api.js";
import { Badge, Banner, Card, Empty, Gauge, HBars, Labels, RelativeTime, Section, Sparkline, StackedBars } from "../components/ui.jsx";
import { navigate } from "../router.js";
import { useApp } from "../store.jsx";

export default function Posture() {
  const { t, data, metrics, health, audience, refresh } = useApp();
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  if (!metrics) return <p className="muted">{t("Loading")}…</p>;

  const incidents = data.incidents || [];
  const open = incidents.filter((item) => item.status === "open");
  const critical = open
    .filter((item) => item.risk === "critical")
    .sort((a, b) => (b.last_seen_at || b.created_at || "").localeCompare(a.last_seen_at || a.created_at || ""));
  const topTeam = metrics.per_team?.[0]?.team;
  const topCategory = metrics.per_category?.[0]?.category;
  const summary = critical.length
    ? t("{critical} critical open · top team {team} · mostly {category}", {
        critical: critical.length,
        team: topTeam || "—",
        category: topCategory || "—",
      })
    : open.length
      ? t("{open} open incidents, none critical", { open: open.length })
      : t("All quiet. No open incidents.");

  async function test(event) {
    event.preventDefault();
    if (!prompt.trim()) return;
    setBusy(true);
    try {
      const scan = await api.scan({ text: prompt, employee_id: data.employees?.[0]?.id, destination: "dashboard", record: true });
      setResult(scan);
      refresh();
    } catch (err) {
      setResult({ error: String(err.message || err) });
    } finally {
      setBusy(false);
    }
  }

  const tests = metrics.tests_last_run || health?.tests_last_run;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Security posture")}</h1>
          <p className="lead">{summary}</p>
        </div>
        <div className="page-head-aside">
          <Gauge value={metrics.posture.score} label={t("Posture score")} />
        </div>
      </div>

      {health?.degraded ? (
        <Banner tone="warn">
          {t("Degraded mode: the semantic model is not loaded. Deterministic checks (PESEL, NIP, IBAN, Luhn, secrets, signatures) still run; free-text names and addresses may slip through.")}
        </Banner>
      ) : (
        <Banner tone="ok">{t("Semantic model loaded (Laya).")}</Banner>
      )}

      <div className="cards">
        <Card label={t("Blocked")} value={metrics.today.block} hint={t("Today")} tone="block" onClick={() => navigate("incidents", { action: "block" })} />
        <Card label={t("Redacted")} value={metrics.today.redact} hint={t("Today")} tone="redact" onClick={() => navigate("incidents", { action: "redact" })} />
        <Card label={t("Allowed")} value={metrics.today.allow} hint={t("Today")} tone="allow" />
        <Card label={t("Open incidents")} value={metrics.incidents.open} hint={`${metrics.incidents.open_critical} ${t("critical")}`} tone={metrics.incidents.open_critical ? "danger" : ""} onClick={() => navigate("incidents", { status: "open" })} />
        <Card label={t("Attacks")} value={metrics.totals.attacks} hint={`${metrics.incidents.open_attacks} ${t("open")}`} tone={metrics.incidents.open_attacks ? "danger" : ""} onClick={() => navigate("incidents", { kind: "attack" })} />
        <Card label={t("Budget used")} value={`${metrics.budget?.totals?.tokens ?? 0}`} hint={`${t("Tokens")} · ${metrics.budget?.exceeded?.length || 0} ${t("Over budget").toLowerCase()}`} tone={metrics.budget?.exceeded?.length ? "danger" : ""} onClick={() => navigate("budget")} />
      </div>

      <div className="grid-2">
        <Section title={t("Decisions, last 24 h")}>
          <StackedBars rows={metrics.hourly} keys={["block", "redact", "allow"]} labels={{ block: t("Blocked"), redact: t("Redacted"), allow: t("Allowed") }} />
        </Section>
        <Section title={t("Alerts, last 15 min")} aside={<span className="muted small">{t("Requests / min")}: {metrics.rpm} · {t("Scan latency")} p95 {metrics.latency_ms.p95} ms</span>}>
          <Sparkline points={metrics.last_15_min} height={120} tone="danger" />
          <div className="spark-labels muted small">
            <span>{metrics.last_15_min[0]?.minute}</span>
            <span>{metrics.last_15_min[metrics.last_15_min.length - 1]?.minute}</span>
          </div>
        </Section>
      </div>

      <div className="grid-3">
        <Section title={t("By team")}>
          <HBars rows={metrics.per_team} labelKey="team" onClick={(row) => navigate("incidents", { team: row.team })} />
        </Section>
        <Section title={t("By destination")}>
          <HBars rows={metrics.per_destination} labelKey="destination" onClick={(row) => navigate("incidents", { destination: row.destination })} tone="accent" />
        </Section>
        <Section title={t("By category")}>
          <HBars rows={metrics.per_category} labelKey="category" onClick={(row) => navigate("incidents", { category: row.category })} tone="warn" />
        </Section>
      </div>

      <div className="grid-2">
        <Section title={t("Latest critical")}>
          {!critical.length && <Empty>{t("All quiet. No open incidents.")}</Empty>}
          {critical.slice(0, 5).map((item) => (
            <article key={item.id} className={`incident ${item.action} compact clickable`} onClick={() => navigate("incidents", { id: item.id })}>
              <div className="row">
                <strong>{item.employee_name}</strong>
                <Badge tone={item.risk}>{t(item.risk)}</Badge>
                <Badge tone={item.action}>{t(item.action)}</Badge>
                {item.kind && item.kind !== "pii" && <Badge tone="attack">{item.kind}</Badge>}
                <span className="muted">{item.destination}</span>
                <span className="muted right">
                  <RelativeTime value={item.last_seen_at || item.created_at} />
                </span>
              </div>
              <p className="muted small">
                {item.team} · {item.role_name} · <Labels items={item.labels} />
              </p>
            </article>
          ))}
        </Section>
        <Section title={t("People with most alerts")}>
          {!metrics.top_people.length && <Empty />}
          {metrics.top_people.map((person) => (
            <div key={person.employee_id} className="row person-row clickable" onClick={() => navigate("incidents", { employee: person.employee_id })}>
              <strong>{person.employee_name}</strong>
              <span className="muted right">{person.count}</span>
            </div>
          ))}
          {audience === "security" && metrics.posture.deductions.length > 0 && (
            <>
              <h3 className="mt">{t("Deductions")}</h3>
              <ul className="deductions">
                {metrics.posture.deductions.map((item) => (
                  <li key={item.reason}>
                    <span className="danger">−{item.points}</span> {item.reason}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      </div>

      <Section title={t("Paste a prompt to test the gate")}>
        <form onSubmit={test} className="row">
          <input
            className="grow"
            placeholder="Anna Kowalska, PESEL 44051401359, mail anna@example.com"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
          <button className="btn" type="submit" disabled={busy}>
            {busy ? t("Scanning…") : t("Test prompt")}
          </button>
        </form>
        {result && !result.error && (
          <div className={`incident ${result.action} mt`}>
            <div className="row">
              <Badge tone={result.action}>{t(result.action)}</Badge>
              <Badge tone={result.risk}>{t(result.risk)}</Badge>
              <span className="muted small">
                {t("Controls fired")}: {(result.controls_fired || []).join(", ") || "—"} · {result.latency_ms} ms · {t("Policy version")} {result.policy_version}
              </span>
            </div>
            <pre>{result.redacted}</pre>
          </div>
        )}
        {result?.error && <p className="danger">{result.error}</p>}
      </Section>

      <div className="statusbar">
        {tests ? (
          <span className={tests.failed ? "danger" : "ok"}>
            {t("Tests: {passed} passed, {failed} failed", { passed: tests.passed, failed: tests.failed })} · <RelativeTime value={tests.finished_at} />
          </span>
        ) : (
          <span className="muted">{t("No test run recorded. Run pytest.")}</span>
        )}
        <span className="muted">
          {t("Scan latency")}: {metrics.latency_ms.last} ms · avg {metrics.latency_ms.avg} · p95 {metrics.latency_ms.p95}
        </span>
        <span className="muted">
          {health?.backend} · {t("Preset: {preset}", { preset: health?.policy_preset })} · v{health?.policy_version}
        </span>
      </div>
    </div>
  );
}
