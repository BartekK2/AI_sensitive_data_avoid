import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Empty, RelativeTime, Section } from "../components/ui.jsx";
import { hrefFor } from "../router.js";
import { useApp } from "../store.jsx";

export default function Policy() {
  const { t, data, health, refresh } = useApp();
  const [policy, setPolicy] = useState(null);
  const [raw, setRaw] = useState("");
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const pol = await api.policy();
    setPolicy(pol);
    if (!editing) setRaw(JSON.stringify(pol.policy, null, 2));
  }, [editing]);

  useEffect(() => {
    load();
  }, [load, health?.policy_version]);

  if (!policy) return <p className="muted">{t("Loading")}…</p>;
  const pol = policy.policy;
  const controls = policy.controls.filter((item) => !/budget/i.test(`${item.id} ${item.label}`));
  const enabled = controls.filter((item) => item.enabled);
  const disabled = controls.filter((item) => !item.enabled);

  async function saveRaw() {
    try {
      const parsed = JSON.parse(raw);
      await api.putPolicy(parsed);
      setEditing(false);
      setError("");
      await Promise.all([load(), refresh()]);
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Effective policy")}</h1>
          <p className="lead">{t("Changes apply on the next request. No restart needed.")}</p>
        </div>
        <div className="page-head-aside actions">
          <a className="btn ghost" href={api.policyExportUrl()} download>
            {t("Export policy.json")}
          </a>
        </div>
      </div>

      <div className="cards">
        <div className="card">
          <div className="card-label">{t("Version")}</div>
          <b>v{pol.version}</b>
          <div className="muted small">{pol.updated_by} · <RelativeTime value={pol.updated_at} /></div>
        </div>
        <div className="card">
          <div className="card-label">{t("Preset: {preset}", { preset: "" })}</div>
          <b>{pol.preset}</b>
          <div className="muted small">{t("Threshold")} {pol.threshold} · strict {String(pol.strict)}</div>
        </div>
        <div className="card">
          <div className="card-label">{t("Controls")}</div>
          <b>{enabled.length}/{controls.length}</b>
          <div className="muted small">{disabled.length ? disabled.map((item) => item.id).join(", ") : t("All")}</div>
        </div>
        <div className="card">
          <div className="card-label">{t("Allowed models")}</div>
          <b>{pol.allowed_models.length || "∞"}</b>
          <div className="muted small">{pol.allowed_models.slice(0, 3).join(", ")}</div>
        </div>
        <div className="card">
          <div className="card-label">{t("Policy file")}</div>
          <b className="small mono">{policy.path.split(/[\\/]/).slice(-2).join("/")}</b>
          <div className="muted small">
            {t("Last reload")}: <RelativeTime value={new Date(policy.mtime * 1000).toISOString()} />
          </div>
        </div>
      </div>

      <div className="grid-2">
        <Section title={t("Controls")}>
          <div className="chips">
            {controls.map((control) => (
              <span key={control.id} className={`chip ${control.enabled ? "ok" : "off"}`} title={control.description}>
                {control.label}
              </span>
            ))}
          </div>
          <h3 className="mt">{t("Actions per category")}</h3>
          <div className="chips">
            {Object.entries(pol.category_actions).map(([key, action]) => (
              <span key={key} className="chip">
                <code>{key}</code> → <Badge tone={action}>{t(action)}</Badge>
              </span>
            ))}
          </div>
          <h3 className="mt">{t("Destination overrides")}</h3>
          {!Object.keys(pol.destination_overrides).length && <Empty />}
          {Object.entries(pol.destination_overrides).map(([dest, overrides]) => (
            <div key={dest} className="row small">
              <b>{dest}</b>
              {Object.entries(overrides).map(([key, action]) => (
                <span key={key}>
                  <code>{key}</code>→{t(action)}
                </span>
              ))}
              {!Object.keys(overrides).length && <span className="muted">—</span>}
            </div>
          ))}
          <h3 className="mt">{t("Agent guardrails")}</h3>
          <p className="small">
            {t("Loop guard")}: {pol.agent.loop_max_repeats}× / {pol.agent.loop_window_s}s · {t("Memory isolation")}: {String(pol.agent.memory_isolation)} · {t("Tool allow-list")}:{" "}
            {pol.agent.allowed_tools ? pol.agent.allowed_tools.join(", ") || "∅" : t("All")}
          </p>
          <p className="muted small mt">
            <a className="link" href={hrefFor("controls")}>
              {t("Controls")}
            </a>{" "}
            ·{" "}
            <a className="link" href={hrefFor("roles")}>
              {t("Roles")}
            </a>{" "}
            ·{" "}
            <a className="link" href={hrefFor("whitelist")}>
              {t("Whitelist")}
            </a>
          </p>
        </Section>

        <Section title={t("Change history")}>
          {!policy.history.length && <Empty />}
          <ul className="timeline">
            {policy.history.map((row, index) => (
              <li key={index}>
                <RelativeTime value={row.ts} /> <Badge tone={row.actor === "disk" ? "warn" : "neutral"}>{row.actor}</Badge> {row.change}{" "}
                {row.version !== undefined && <span className="muted small">v{row.version}</span>}
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <Section
        title="policy.json"
        aside={
          editing ? (
            <div className="actions">
              <button className="btn ghost" onClick={() => { setEditing(false); setRaw(JSON.stringify(pol, null, 2)); setError(""); }}>
                {t("Cancel")}
              </button>
              <button className="btn" onClick={saveRaw}>
                {t("Save")}
              </button>
            </div>
          ) : (
            <button className="btn ghost" onClick={() => setEditing(true)}>
              {t("Edit")}
            </button>
          )
        }
      >
        <textarea className="mono" rows={18} value={raw} readOnly={!editing} onChange={(event) => setRaw(event.target.value)} />
        {error && <p className="danger">{error}</p>}
      </Section>

      <p className="muted small">{t("Roles")}: {(data.roles || []).map((role) => role.name).join(", ")}</p>
    </div>
  );
}
