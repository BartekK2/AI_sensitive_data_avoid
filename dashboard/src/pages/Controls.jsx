import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Empty, RelativeTime, Section, Select, useConfirm } from "../components/ui.jsx";
import { useApp } from "../store.jsx";

const ACTIONS = ["allow", "redact", "block"];
const SAMPLE = "Anna Kowalska, tel +48 600 100 200, PESEL 44051401359, mail anna@example.com, IBAN PL61109010140000071219812874";

export default function Controls() {
  const { t, data, refresh, health } = useApp();
  const [controls, setControls] = useState([]);
  const [policy, setPolicy] = useState(null);
  const [sample, setSample] = useState(SAMPLE);
  const [threshold, setThreshold] = useState(null);
  const [preview, setPreview] = useState(null);
  const [newModel, setNewModel] = useState("");
  const [newDest, setNewDest] = useState("");
  const [ask, confirmEl] = useConfirm();

  const load = useCallback(async () => {
    const [list, pol] = await Promise.all([api.controls(), api.policy()]);
    setControls(list);
    setPolicy(pol);
    setThreshold((current) => (current === null ? pol.policy.threshold : current));
  }, []);

  useEffect(() => {
    load();
  }, [load, health?.policy_version]);

  useEffect(() => {
    if (threshold === null) return undefined;
    const timer = setTimeout(async () => {
      try {
        const [low, high, current] = await Promise.all([
          api.scan({ text: sample, threshold: 0.3 }),
          api.scan({ text: sample, threshold: 0.8 }),
          api.scan({ text: sample, threshold }),
        ]);
        setPreview({ low, high, current });
      } catch {
        setPreview(null);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [sample, threshold]);

  if (!policy) return <p className="muted">{t("Loading")}…</p>;
  const pol = policy.policy;
  const categories = (data.categories || []).map((item) => item.key).concat(["attack"]);

  async function toggleControl(control) {
    if (control.enabled && control.critical) {
      const ok = await ask({
        title: t("Disable"),
        body: t("Disabling this control lets {what} through. Continue?", { what: t("critical identifiers (PESEL, cards, secrets)") }),
        confirmLabel: t("Disable"),
      });
      if (!ok) return;
    }
    await api.patchControl(control.id, { enabled: !control.enabled });
    await Promise.all([load(), refresh()]);
  }

  async function patch(body) {
    await api.patchPolicy(body);
    await Promise.all([load(), refresh()]);
  }

  async function setCategoryAction(key, action) {
    const next = { ...pol.category_actions };
    if (action) next[key] = action;
    else delete next[key];
    await patch({ category_actions: next });
  }

  async function setDestinationAction(dest, key, action) {
    const next = { ...pol.destination_overrides, [dest]: { ...(pol.destination_overrides[dest] || {}) } };
    if (action) next[dest][key] = action;
    else delete next[dest][key];
    await patch({ destination_overrides: next });
  }

  async function removeDestination(dest) {
    const next = { ...pol.destination_overrides };
    delete next[dest];
    await patch({ destination_overrides: next });
  }

  const deterministic = controls.filter((item) => item.type === "deterministic");
  const semantic = controls.filter((item) => item.type === "semantic");

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Control catalog")}</h1>
          <p className="lead">{t("Changes apply on the next request. No restart needed.")}</p>
        </div>
        <div className="page-head-aside">
          <div className="segmented">
            {policy.presets.map((name) => (
              <button key={name} className={pol.preset === name ? "active" : ""} onClick={() => patch({ preset: name })}>
                {name}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <Section title={t("Deterministic (non-AI)")}>
          <ControlTable rows={deterministic} t={t} onToggle={toggleControl} />
        </Section>
        <Section title={t("Semantic (AI-based)")}>
          <ControlTable rows={semantic} t={t} onToggle={toggleControl} />
          <p className="muted small mt">
            {health?.backend === "laya" ? t("Semantic model loaded (Laya).") : t("Degraded mode: the semantic model is not loaded. Deterministic checks (PESEL, NIP, IBAN, Luhn, secrets, signatures) still run; free-text names and addresses may slip through.")}
          </p>
        </Section>
      </div>

      <Section
        title={t("Threshold preview")}
        aside={
          <label className="row">
            <span className="muted small">{t("Threshold")}</span>
            <input type="range" min="0" max="1" step="0.05" value={threshold ?? pol.threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
            <b>{(threshold ?? pol.threshold).toFixed(2)}</b>
            <button className="btn ghost" onClick={() => patch({ threshold })} disabled={threshold === pol.threshold}>
              {t("Save")}
            </button>
          </label>
        }
      >
        <textarea rows={2} value={sample} onChange={(event) => setSample(event.target.value)} placeholder={t("Sample text")} />
        {preview && (
          <div className="grid-3 mt">
            {[
              ["0.30", preview.low],
              [(threshold ?? pol.threshold).toFixed(2), preview.current],
              ["0.80", preview.high],
            ].map(([label, scan]) => (
              <div key={label} className={`panel ${scan.action}`}>
                <div className="row">
                  <b>{t("Entities at {t}", { t: label })}</b>
                  <Badge tone={scan.action}>{t(scan.action)}</Badge>
                </div>
                <ul className="plain">
                  {(scan.entities || []).map((entity, index) => (
                    <li key={index}>
                      <code>{entity.label}</code> <span className="muted small">{entity.score?.toFixed?.(2)}</span>
                    </li>
                  ))}
                  {!scan.entities?.length && <li className="muted">—</li>}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Section>

      <div className="grid-2">
        <Section title={t("Actions per category")}>
          <table className="compact">
            <tbody>
              {categories.map((key) => (
                <tr key={key}>
                  <td>
                    <code>{key}</code>
                  </td>
                  <td>
                    <div className="segmented small">
                      <button className={!pol.category_actions[key] ? "active" : ""} onClick={() => setCategoryAction(key, "")}>
                        auto
                      </button>
                      {ACTIONS.map((action) => (
                        <button key={action} className={`${pol.category_actions[key] === action ? "active" : ""} ${action}`} onClick={() => setCategoryAction(key, action)}>
                          {t(action)}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">auto = {t("Risk")} → {t("Action")} (critical → block, high/medium → redact, low → {pol.strict ? "redact" : "allow"})</p>
        </Section>

        <Section
          title={t("Destination overrides")}
          aside={
            <form
              className="row"
              onSubmit={async (event) => {
                event.preventDefault();
                if (!newDest.trim()) return;
                await patch({ destination_overrides: { ...pol.destination_overrides, [newDest.trim()]: {} } });
                setNewDest("");
              }}
            >
              <input placeholder="chatgpt.com" value={newDest} onChange={(event) => setNewDest(event.target.value)} />
              <button className="btn ghost" type="submit">
                {t("Add destination")}
              </button>
            </form>
          }
        >
          {!Object.keys(pol.destination_overrides).length && <Empty />}
          {Object.entries(pol.destination_overrides).map(([dest, overrides]) => (
            <div key={dest} className="panel mb">
              <div className="row">
                <b>{dest}</b>
                <span className="grow" />
                <button className="link danger" onClick={() => removeDestination(dest)}>
                  {t("Delete")}
                </button>
              </div>
              <div className="chips mt">
                {categories.map((key) => (
                  <label key={key} className="chip">
                    <span>{key}</span>
                    <Select value={overrides[key] || ""} onChange={(value) => setDestinationAction(dest, key, value)} placeholder="—" options={ACTIONS.map((action) => [action, t(action)])} />
                  </label>
                ))}
              </div>
            </div>
          ))}
        </Section>
      </div>

      <div className="grid-2">
        <Section
          title={t("Allowed models")}
          aside={
            <form
              className="row"
              onSubmit={async (event) => {
                event.preventDefault();
                if (!newModel.trim()) return;
                await patch({ allowed_models: [...pol.allowed_models, newModel.trim()] });
                setNewModel("");
              }}
            >
              <input placeholder="gpt-4o-mini / claude-3* / llama3*" value={newModel} onChange={(event) => setNewModel(event.target.value)} />
              <button className="btn ghost" type="submit">
                {t("Add model")}
              </button>
            </form>
          }
        >
          <p className="muted small">{t("Empty list means every model is allowed.")}</p>
          <div className="chips">
            {pol.allowed_models.map((model) => (
              <span key={model} className="chip">
                <code>{model}</code>
                <button className="link danger" onClick={() => patch({ allowed_models: pol.allowed_models.filter((item) => item !== model) })}>
                  ×
                </button>
              </span>
            ))}
          </div>
        </Section>
        <Section title={t("Scan model responses")}>
          <label className="check">
            <input type="checkbox" checked={pol.scan_output} onChange={(event) => patch({ scan_output: event.target.checked })} /> {t("Scan model responses")}
          </label>
          <label className="check">
            <input type="checkbox" checked={pol.strict} onChange={(event) => patch({ strict: event.target.checked })} /> strict ({t("low")} → {t("redact")})
          </label>
        </Section>
      </div>
      {confirmEl}
    </div>
  );
}

function ControlTable({ rows, t, onToggle }) {
  return (
    <table className="compact controls">
      <thead>
        <tr>
          <th></th>
          <th>{t("Controls")}</th>
          <th>{t("Hits")}</th>
          <th>{t("Last hit")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((control) => (
          <tr key={control.id} className={control.enabled ? "" : "disabled"}>
            <td>
              <label className="switch">
                <input type="checkbox" checked={control.enabled} onChange={() => onToggle(control)} />
                <span />
              </label>
            </td>
            <td>
              <b>{control.label}</b> {control.critical && <Badge tone="critical">{t("critical")}</Badge>}
              <div className="muted small">{control.description}</div>
            </td>
            <td>{control.hits}</td>
            <td className="muted small">
              <RelativeTime value={control.last_hit} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
