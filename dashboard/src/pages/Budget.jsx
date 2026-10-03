import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Banner, Empty, Progress, Section, useConfirm } from "../components/ui.jsx";
import { hrefFor } from "../router.js";
import { useApp } from "../store.jsx";

export default function Budget() {
  const { t, audience, health, refresh, toast } = useApp();
  const [summary, setSummary] = useState(null);
  const [budgets, setBudgets] = useState(null);
  const [draft, setDraft] = useState(null);
  const [ask, confirmEl] = useConfirm();

  const load = useCallback(async () => {
    const [sum, pol] = await Promise.all([api.budget(), api.policy()]);
    setSummary(sum);
    setBudgets(pol.policy.budgets);
    setDraft((current) => current || pol.policy.budgets);
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load, health?.policy_version]);

  if (!summary || !budgets || !draft) return <p className="muted">{t("Loading")}…</p>;

  async function save(next) {
    await api.patchPolicy({ budgets: next });
    setDraft(next);
    await Promise.all([load(), refresh()]);
    toast({ title: t("Saved"), tone: "ok" });
  }

  async function setLimit(scope, key, value) {
    const limits = { ...draft.limits, [scope]: { ...draft.limits[scope] } };
    if (value === "" || value === null) delete limits[scope][key];
    else limits[scope][key] = Number(value);
    await save({ ...draft, limits });
  }

  async function setCost(model, value) {
    const cost = { ...draft.cost_per_1k };
    if (value === "") delete cost[model];
    else cost[model] = Number(value);
    await save({ ...draft, cost_per_1k: cost });
  }

  async function toggleLocal(model) {
    const local = draft.local_models.includes(model) ? draft.local_models.filter((item) => item !== model) : [...draft.local_models, model];
    await save({ ...draft, local_models: local });
  }

  async function resetUsage() {
    if (await ask({ title: t("Reset usage"), body: t("This cannot be undone.") })) {
      await api.resetBudget();
      await load();
    }
  }

  const totalSplit = summary.split.local + summary.split.cloud || 1;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Budget")}</h1>
          <p className="lead">{t("Tokens are estimated as characters / 4. Cost uses the per-model price table.")}</p>
        </div>
        <div className="page-head-aside actions">
          <label className="check">
            <input type="checkbox" checked={draft.enabled} onChange={(event) => save({ ...draft, enabled: event.target.checked })} /> {t("Enabled")}
          </label>
          <button className="btn ghost" onClick={resetUsage}>
            {t("Reset usage")}
          </button>
        </div>
      </div>

      {summary.exceeded.length > 0 && (
        <Banner tone="critical">
          {t("Over budget")}: {summary.exceeded.join(", ")} — {t("requests return 429 until midnight or reset.")}
        </Banner>
      )}
      {summary.warnings.length > 0 && (
        <Banner tone="warn">
          {t("Warning at {pct}%", { pct: summary.alert_pct })}: {summary.warnings.map((item) => `${item.label} (${item.pct}%)`).join(", ")}
        </Banner>
      )}

      <div className="cards">
        <div className="card">
          <div className="card-label">{t("Tokens today")}</div>
          <b>{summary.totals.tokens.toLocaleString()}</b>
          <div className="muted small">{summary.date}</div>
        </div>
        <div className="card">
          <div className="card-label">{t("Estimated cost")}</div>
          <b>${summary.totals.cost.toFixed(4)}</b>
          <div className="muted small">{t("per 1k tokens table")}</div>
        </div>
        <div className="card">
          <div className="card-label">{t("Requests")}</div>
          <b>{summary.totals.requests}</b>
          <div className="muted small">
            {t("blocked")}: {summary.totals.blocked}
          </div>
        </div>
        <div className="card">
          <div className="card-label">{t("Local vs cloud")}</div>
          <b>
            {Math.round((100 * summary.split.local) / totalSplit)}% / {Math.round((100 * summary.split.cloud) / totalSplit)}%
          </b>
          <div className="progress split">
            <span style={{ width: `${(100 * summary.split.local) / totalSplit}%` }} />
          </div>
        </div>
        <div className="card">
          <div className="card-label">{t("Rate limit")}</div>
          <b>{summary.requests_per_min}/min</b>
          <div className="muted small">{t("per person")}</div>
        </div>
      </div>

      <div className="grid-2">
        <Section title={t("People")}>
          <UsageTable
            rows={summary.employees}
            t={t}
            editable
            onLimit={(key, value) => setLimit("employees", key, value)}
            linkFor={(row) => hrefFor("people", { id: row.key })}
          />
        </Section>
        <Section title={t("Teams")}>
          <UsageTable rows={summary.teams} t={t} editable onLimit={(key, value) => setLimit("teams", key, value)} />
        </Section>
      </div>

      <Section title={t("Models")}>
        <table className="compact">
          <thead>
            <tr>
              <th>{t("Model")}</th>
              <th>{t("Tokens")}</th>
              <th>{t("Limit")}</th>
              <th>{t("Cost per 1k")}</th>
              <th>{t("Local")}</th>
              <th>{t("Usage")}</th>
            </tr>
          </thead>
          <tbody>
            {!summary.models.length && (
              <tr>
                <td colSpan={6}>
                  <Empty />
                </td>
              </tr>
            )}
            {summary.models.map((row) => (
              <tr key={row.key}>
                <td>
                  <code>{row.key}</code>
                </td>
                <td>{row.tokens.toLocaleString()}</td>
                <td>
                  <LimitInput value={draft.limits.models[row.key]} fallback={row.limit} onCommit={(value) => setLimit("models", row.key, value)} />
                </td>
                <td>
                  <LimitInput value={draft.cost_per_1k[row.key]} fallback={draft.cost_per_1k.default ?? 0} step="0.0001" onCommit={(value) => setCost(row.key, value)} />
                </td>
                <td>
                  <input type="checkbox" checked={draft.local_models.includes(row.key) || row.local} onChange={() => toggleLocal(row.key)} />
                </td>
                <td className="w-200">
                  <Progress pct={row.pct} alert={summary.alert_pct} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {audience === "security" && (
        <Section title={t("Defaults")}>
          <div className="grid">
            <label>
              {t("Default per person")}
              <input type="number" defaultValue={draft.default_tokens_per_day} onBlur={(event) => save({ ...draft, default_tokens_per_day: Number(event.target.value) })} />
            </label>
            <label>
              {t("Default per team")}
              <input type="number" defaultValue={draft.default_team_tokens_per_day} onBlur={(event) => save({ ...draft, default_team_tokens_per_day: Number(event.target.value) })} />
            </label>
            <label>
              {t("Default per model")}
              <input type="number" defaultValue={draft.default_model_tokens_per_day} onBlur={(event) => save({ ...draft, default_model_tokens_per_day: Number(event.target.value) })} />
            </label>
            <label>
              {t("Rate limit")} (/min)
              <input type="number" defaultValue={draft.requests_per_min} onBlur={(event) => save({ ...draft, requests_per_min: Number(event.target.value) })} />
            </label>
            <label>
              {t("Warning at {pct}%", { pct: "" })}
              <input type="number" defaultValue={draft.alert_pct} onBlur={(event) => save({ ...draft, alert_pct: Number(event.target.value) })} />
            </label>
            <label>
              {t("Local models")} (comma separated)
              <input defaultValue={draft.local_models.join(", ")} onBlur={(event) => save({ ...draft, local_models: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} />
            </label>
          </div>
        </Section>
      )}
      {confirmEl}
    </div>
  );
}

function UsageTable({ rows, t, editable, onLimit, linkFor }) {
  if (!rows.length) return <Empty />;
  return (
    <table className="compact">
      <thead>
        <tr>
          <th>{t("Name")}</th>
          <th>{t("Tokens")}</th>
          <th>{t("Limit")}</th>
          <th>{t("Usage")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={row.pct >= 100 ? "stale" : ""}>
            <td>
              {linkFor ? (
                <a className="link" href={linkFor(row)}>
                  {row.label}
                </a>
              ) : (
                row.label
              )}
              {row.team && <span className="muted small"> · {row.team}</span>}
              {row.blocked > 0 && <Badge tone="block">{row.blocked} {t("blocked")}</Badge>}
            </td>
            <td>
              {row.tokens.toLocaleString()} <span className="muted small">${row.cost.toFixed(4)}</span>
            </td>
            <td>{editable ? <LimitInput value={row.limit} fallback={row.limit} onCommit={(value) => onLimit(row.key, value)} /> : row.limit}</td>
            <td className="w-200">
              <Progress pct={row.pct} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LimitInput({ value, fallback, step = "1000", onCommit }) {
  const [text, setText] = useState(value ?? "");
  useEffect(() => setText(value ?? ""), [value]);
  return (
    <input
      className="limit"
      type="number"
      step={step}
      placeholder={String(fallback ?? "")}
      value={text}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => {
        if (String(text) !== String(value ?? "")) onCommit(text);
      }}
      onKeyDown={(event) => event.key === "Enter" && event.target.blur()}
    />
  );
}
