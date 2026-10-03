import { Badge, Section } from "../components/ui.jsx";
import { hrefFor } from "../router.js";
import { useApp } from "../store.jsx";

export default function Architecture() {
  const { t, health, metrics } = useApp();
  const inputs = health?.inputs || {};
  const laya = health?.laya_loaded;

  const INPUTS = [
    { id: "extension", label: t("Browser extension"), on: inputs.extension, note: "chatgpt.com / claude.ai / gemini → POST /v1/scan" },
    { id: "netgate", label: t("HTTP gateway"), on: inputs.netgate, note: "/net/openai, /net/anthropic, /net/gemini, /net/ollama" },
    { id: "proxy", label: t("Forward proxy"), on: inputs.proxy, note: inputs.proxy_port ? `:${inputs.proxy_port}` : t("start with `sensitive-guard net`") },
    { id: "mitm", label: "TLS MITM", on: inputs.mitm, note: t("optional, for apps that ignore HTTP_PROXY") },
  ];

  const STAGES = [
    ["model_allowlist", t("Model allow-list"), "403"],
    ["rate_limit", t("Rate limit"), "429"],
    ["budget", t("Budget"), "429"],
    ["loop_guard", t("Loop guard"), "429"],
    ["tool_allowlist", t("Tool allow-list"), "403"],
    ["memory_isolation", t("Memory isolation"), "403"],
    ["finder", t("Deterministic finder"), "regex + checksum"],
    ["classifier", t("Semantic classifier"), laya ? "Laya" : t("degraded")],
    ["signatures", t("Attack signatures"), "403"],
    ["policy", t("Policy"), t("allow / redact / block")],
    ["output", t("Response scan"), t("redact")],
    ["record", t("Audit + telemetry"), "jsonl + ring"],
  ];

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Architecture")}</h1>
          <p className="lead">{t("Every path to a model passes the same gate. Deterministic checks run first; the AI classifier only sees what they propose.")}</p>
        </div>
      </div>

      <Section title={t("Inputs (live)")}>
        <div className="cards">
          {INPUTS.map((input) => (
            <div key={input.id} className={`card ${input.on ? "ok" : ""}`}>
              <div className="card-label">{input.label}</div>
              <b>
                <Badge tone={input.on ? "ok" : "neutral"}>{input.on ? t("active") : t("inactive")}</Badge>
              </b>
              <div className="muted small">{input.note}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title={t("Pipeline")}>
        <ol className="pipeline">
          {STAGES.map(([id, label, note]) => (
            <li key={id}>
              <b>{label}</b>
              <span className="muted small">{note}</span>
            </li>
          ))}
        </ol>
      </Section>

      <div className="grid-2">
        <Section title={t("Why hybrid")}>
          <ul>
            <li>{t("Deterministic: PESEL/NIP/IBAN checksums, Luhn, secret formats, regex signatures. Explainable, 0 false negatives on known formats.")}</li>
            <li>{t("Semantic: Laya PII expert classifies spans the finder proposes (names, addresses, context). Threshold adjustable live.")}</li>
            <li>{t("If the model is missing, the gate stays up in degraded mode and the dashboard says so.")}</li>
          </ul>
        </Section>
        <Section title={t("Data at rest")}>
          <table className="compact">
            <tbody>
              <tr>
                <td>data/policy.json</td>
                <td className="muted small">{t("hot-reload by mtime")} · v{health?.policy_version}</td>
              </tr>
              <tr>
                <td>data/signatures.json</td>
                <td className="muted small">{health?.signatures_count} {t("Signatures").toLowerCase()}</td>
              </tr>
              <tr>
                <td>data/audit.jsonl</td>
                <td className="muted small">{t("append-only")}</td>
              </tr>
              <tr>
                <td>data/workspace.json</td>
                <td className="muted small">{t("people, roles, categories, incidents, usage")}</td>
              </tr>
              <tr>
                <td>{t("telemetry")}</td>
                <td className="muted small">
                  {t("in-memory")} · {metrics?.ring_size} {t("events")}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="muted small">
            <a className="link" href={hrefFor("policy")}>
              {t("Effective policy")}
            </a>{" "}
            ·{" "}
            <a className="link" href={hrefFor("telemetry")}>
              {t("Telemetry")}
            </a>
          </p>
        </Section>
      </div>
    </div>
  );
}
