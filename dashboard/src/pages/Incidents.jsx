import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Badge, Drawer, Duration, Empty, Filters, Labels, RelativeTime, Select, useConfirm } from "../components/ui.jsx";
import { hrefFor, navigate } from "../router.js";
import { useApp } from "../store.jsx";

const SUGGESTIONS = {
  credentials: "Revoke the key and rotate credentials.",
  government_id: "Notify HR / DPO; the identifier was not sent.",
  financial: "Verify with the owner; card data must never leave.",
  contact: "Confirm the recipient had a business reason.",
  person_name: "Confirm the recipient had a business reason.",
  attack: "Review the agent that produced this prompt.",
  budget: "Raise the budget or stop the runaway job.",
  loop: "Raise the budget or stop the runaway job.",
  rate_limit: "Raise the budget or stop the runaway job.",
  model: "Add the model to the allow-list if it is approved.",
};

const RUNBOOK = {
  credentials: ["Revoke the exposed key in the provider console.", "Rotate dependent secrets and redeploy.", "Confirm with the employee which system the key belonged to."],
  government_id: ["Confirm the request was blocked (nothing left the gate).", "Tell the employee which channel is approved for this data.", "Record the DPO decision in the note."],
  financial: ["Check whether the card or account is a live customer record.", "Notify Finance if it was a customer's.", "Close with a note once ownership is confirmed."],
  attack: ["Identify the agent or tool that produced the prompt.", "Check the signature feed and tighten if needed.", "Review the employee's recent audit trail."],
  budget: ["Check the top spenders view.", "Decide whether to raise the daily limit.", "Stop the job if it is an agent loop."],
  default: ["Review the redacted excerpt.", "Talk to the employee or team lead.", "Close with a note."],
};

function statusTone(status) {
  return status === "open" ? "open" : status === "ack" ? "ack" : status === "false_positive" ? "fp" : "resolved";
}

export default function Incidents() {
  const { t, data, route, refresh, audience } = useApp();
  const params = route.params;
  const [page, setPage] = useState({ items: [], total: 0, facets: { teams: [], destinations: [] } });
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [group, setGroup] = useState(true);
  const [sort, setSort] = useState("created_at");
  const [note, setNote] = useState("");
  const [attempts, setAttempts] = useState([]);
  const [ask, confirmEl] = useConfirm();

  const filters = useMemo(
    () => ({
      status: params.status || "",
      risk: params.risk || "",
      action: params.action || "",
      kind: params.kind || "",
      team: params.team || "",
      employee: params.employee || "",
      destination: params.destination || "",
      category: params.category || "",
      since: params.since || "",
      until: params.until || "",
      q: params.q || "",
    }),
    [params]
  );

  const setFilter = (key, value) => {
    const next = { ...params, [key]: value };
    delete next.id;
    if (!value) delete next[key];
    navigate("incidents", next);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.incidents({ ...filters, sort, order: "desc", limit: 300 });
      setPage(result);
    } finally {
      setLoading(false);
    }
  }, [filters, sort]);

  useEffect(() => {
    load();
  }, [load, data?.stats?.incidents, data?.stats?.open_incidents]);

  // Server-side dedupe merges repeats inside a 5-minute window. Grouping here
  // folds the same person + labels across windows into one row with a summed count.
  const rows = useMemo(() => {
    if (!group) return page.items;
    const seen = new Map();
    const out = [];
    for (const item of page.items) {
      const key = item.dedupe_key || item.id;
      const existing = seen.get(key);
      if (existing && existing.status === item.status) {
        existing.count = (existing.count || 1) + (item.count || 1);
        existing.grouped = (existing.grouped || [existing.id]).concat(item.id);
        continue;
      }
      const copy = { ...item };
      seen.set(key, copy);
      out.push(copy);
    }
    return out;
  }, [page.items, group]);

  const current = params.id ? (data.incidents || []).find((item) => item.id === params.id) : null;

  useEffect(() => {
    setNote(current?.note || "");
    if (current?.employee_id) {
      api
        .audit({ employee: current.employee_id, limit: 10 })
        .then((result) => setAttempts(result.items || []))
        .catch(() => setAttempts([]));
    } else {
      setAttempts([]);
    }
  }, [current?.id, current?.note, current?.employee_id]);

  async function patch(item, body) {
    await api.patchIncident(item.id, body);
    await Promise.all([refresh(), load()]);
  }

  async function bulk(body) {
    if (!selected.size) return;
    await api.bulkIncidents({ ids: [...selected], ...body });
    setSelected(new Set());
    await Promise.all([refresh(), load()]);
  }

  async function demo(action) {
    const ok = await ask({
      title: t("Demo data"),
      body: action === "reset" ? t("Remove seed incidents") + " → " + t("Reset usage") : t("Clear live incidents"),
      tone: "danger",
    });
    if (!ok) return;
    if (action === "reset") await api.demoReset(true);
    else await api.demoClearLive();
    setSelected(new Set());
    await Promise.all([refresh(), load()]);
  }

  function toggle(id) {
    setSelected((set) => {
      const next = new Set(set);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const admins = (data.employees || []).filter((person) => {
    const role = (data.roles || []).find((item) => item.id === person.role_id);
    return role?.level === "admin" || role?.can_override;
  });
  const categories = (data.categories || []).map((item) => item.key);
  const kinds = ["pii", "attack", "budget", "model", "loop", "rate_limit", "memory", "tool"];
  const exportIds = selected.size ? [...selected].join(",") : undefined;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Incidents")}</h1>
          <p className="lead">{t("Every blocked or redacted request lands here with the person, role and control that fired.")}</p>
        </div>
        <div className="page-head-aside actions">
          <a className="btn ghost" href={api.incidentsExportUrl({ format: "csv", ids: exportIds, status: filters.status || undefined })} download>
            {t("Export CSV")}
          </a>
          <a className="btn ghost" href={api.incidentsExportUrl({ format: "jsonl", ids: exportIds, status: filters.status || undefined })} download>
            {t("Export JSONL")}
          </a>
        </div>
      </div>

      <Filters>
        <input className="grow" placeholder={t("Search text, labels, people")} value={filters.q} onChange={(event) => setFilter("q", event.target.value)} />
        <Select value={filters.status} onChange={(value) => setFilter("status", value)} placeholder={`${t("Status")}: ${t("All")}`} options={[["open", t("Open")], ["ack", t("Acknowledged")], ["resolved", t("Resolved")], ["false_positive", t("False positive")]]} />
        <Select value={filters.risk} onChange={(value) => setFilter("risk", value)} placeholder={`${t("Risk")}: ${t("All")}`} options={[["critical", t("critical")], ["high", t("high")], ["medium", t("medium")], ["low", t("low")]]} />
        <Select value={filters.action} onChange={(value) => setFilter("action", value)} placeholder={`${t("Action")}: ${t("All")}`} options={[["block", t("block")], ["redact", t("redact")]]} />
        <Select value={filters.kind} onChange={(value) => setFilter("kind", value)} placeholder={`${t("Kind")}: ${t("All")}`} options={kinds} />
        <Select value={filters.team} onChange={(value) => setFilter("team", value)} placeholder={`${t("Team")}: ${t("All")}`} options={page.facets?.teams || []} />
        <Select value={filters.destination} onChange={(value) => setFilter("destination", value)} placeholder={`${t("Destination")}: ${t("All")}`} options={page.facets?.destinations || []} />
        <Select value={filters.category} onChange={(value) => setFilter("category", value)} placeholder={`${t("Category")}: ${t("All")}`} options={categories} />
        <Select value={filters.employee} onChange={(value) => setFilter("employee", value)} placeholder={`${t("Person")}: ${t("All")}`} options={(data.employees || []).map((person) => [person.id, person.name])} />
        <input type="datetime-local" value={filters.since ? filters.since.slice(0, 16) : ""} onChange={(event) => setFilter("since", event.target.value ? new Date(event.target.value).toISOString() : "")} title={t("Since")} />
        <Select value={sort} onChange={setSort} options={[["created_at", t("Status") + " · " + t("Since")], ["risk", t("Risk")], ["count", t("Count")], ["employee_name", t("Person")], ["team", t("Team")]]} />
        <label className="check">
          <input type="checkbox" checked={group} onChange={(event) => setGroup(event.target.checked)} /> {t("Group repeats")}
        </label>
      </Filters>

      <div className="row toolbar">
        <label className="check">
          <input
            type="checkbox"
            checked={rows.length > 0 && selected.size === rows.length}
            onChange={(event) => setSelected(event.target.checked ? new Set(rows.map((item) => item.id)) : new Set())}
          />{" "}
          {t("Select all")}
        </label>
        <span className="muted small">
          {t("{n} selected", { n: selected.size })} · {page.total} {t("Total").toLowerCase()}
        </span>
        <span className="grow" />
        <button className="btn ghost" disabled={!selected.size} onClick={() => bulk({ status: "ack" })}>
          {t("Acknowledge")}
        </button>
        <button className="btn ghost" disabled={!selected.size} onClick={() => bulk({ status: "resolved" })}>
          {t("Resolve")}
        </button>
        <button className="btn ghost" disabled={!selected.size} onClick={() => bulk({ status: "false_positive" })}>
          {t("Mark false positive")}
        </button>
        {audience === "security" && (
          <>
            <button className="btn ghost small" title={t("Demo data")} onClick={() => demo("clear")}>
              {t("Clear live incidents")}
            </button>
            <button className="btn ghost small" title={t("Demo data")} onClick={() => demo("reset")}>
              {t("Remove seed incidents")}
            </button>
          </>
        )}
      </div>

      {loading && !rows.length && <p className="muted">{t("Loading")}…</p>}
      {!loading && !rows.length && <Empty>{t("Nothing matches these filters.")}</Empty>}

      <div className="incident-list">
        {rows.map((item) => {
          const ageMinutes = (Date.now() - new Date(item.created_at).getTime()) / 60000;
          const stale = item.status === "open" && item.risk === "critical" && ageMinutes > 60;
          return (
            <article key={item.id} className={`incident ${item.action} ${item.status} ${stale ? "stale" : ""} clickable`} onClick={() => navigate("incidents", { ...params, id: item.id })}>
              <div className="row">
                <input type="checkbox" checked={selected.has(item.id)} onClick={(event) => event.stopPropagation()} onChange={() => toggle(item.id)} />
                <strong>{item.employee_name}</strong>
                <Badge tone={statusTone(item.status)}>{t(item.status)}</Badge>
                <Badge tone={item.risk}>{t(item.risk)}</Badge>
                <Badge tone={item.action}>{t(item.action)}</Badge>
                {item.kind && item.kind !== "pii" && <Badge tone="attack">{item.kind}</Badge>}
                {group && item.count > 1 && <Badge tone="count">{t("Seen {n}×", { n: item.count })}</Badge>}
                {item.direction === "output" && <Badge tone="neutral">{t("output")}</Badge>}
                <span className="muted">{item.destination}</span>
                <span className="muted right">
                  <RelativeTime value={item.last_seen_at || item.created_at} />
                </span>
              </div>
              <p className="muted small">
                {item.team} · {item.role_name} · <Labels items={item.labels} /> {item.assignee && <>· {t("Assignee")}: {item.assignee}</>}
              </p>
              <pre className="excerpt">{item.prompt_excerpt || item.redacted}</pre>
              {item.note && <p className="note">{item.note}</p>}
            </article>
          );
        })}
      </div>

      <Drawer open={Boolean(current)} title={current ? `${current.employee_name} · ${current.destination}` : ""} onClose={() => navigate("incidents", { ...params, id: undefined })} wide>
        {current && (
          <IncidentDetail
            item={current}
            t={t}
            admins={admins}
            audience={audience}
            note={note}
            setNote={setNote}
            attempts={attempts}
            onPatch={(body) => patch(current, body)}
            onDelete={async () => {
              if (await ask({ title: t("Delete"), body: t("This cannot be undone.") })) {
                await api.deleteIncident(current.id);
                navigate("incidents", { ...params, id: undefined });
                await Promise.all([refresh(), load()]);
              }
            }}
            roles={data.roles || []}
            employees={data.employees || []}
          />
        )}
      </Drawer>
      {confirmEl}
    </div>
  );
}

function IncidentDetail({ item, t, admins, audience, note, setNote, attempts, onPatch, onDelete, roles, employees }) {
  const employee = employees.find((person) => person.id === item.employee_id);
  const role = roles.find((entry) => entry.name === item.role_name) || roles.find((entry) => entry.id === employee?.role_id);
  const primary = item.kind && item.kind !== "pii" ? item.kind : item.categories?.[0];
  const suggestion = SUGGESTIONS[primary] || "Close as test if this was a drill.";
  const runbook = RUNBOOK[primary] || RUNBOOK.default;

  return (
    <div className="detail">
      <div className="row">
        <Badge tone={statusTone(item.status)}>{t(item.status)}</Badge>
        <Badge tone={item.risk}>{t(item.risk)}</Badge>
        <Badge tone={item.action}>{t(item.action)}</Badge>
        {item.kind && <Badge tone={item.kind === "pii" ? "neutral" : "attack"}>{item.kind}</Badge>}
        {item.count > 1 && <Badge tone="count">{t("Seen {n}×", { n: item.count })}</Badge>}
        <span className="muted right">
          <Duration since={item.created_at} />
        </span>
      </div>

      <dl className="facts">
        <dt>{t("Person")}</dt>
        <dd>
          {item.employee_name}{" "}
          {item.employee_id && (
            <a className="link" href={hrefFor("people", { id: item.employee_id })}>
              {t("View person")}
            </a>
          )}
        </dd>
        <dt>{t("Role")}</dt>
        <dd>
          {item.role_name}{" "}
          {role && (
            <a className="link" href={hrefFor("roles", { id: role.id })}>
              {t("View role")}
            </a>
          )}
        </dd>
        <dt>{t("Team")}</dt>
        <dd>{item.team}</dd>
        <dt>{t("Destination")}</dt>
        <dd>
          {item.destination} {item.model && <code>{item.model}</code>}
        </dd>
        <dt>{t("Since")}</dt>
        <dd>
          <RelativeTime value={item.created_at} /> <span className="muted small">{item.created_at}</span>
        </dd>
        {item.policy_version !== undefined && (
          <>
            <dt>{t("Policy version")}</dt>
            <dd>v{item.policy_version}</dd>
          </>
        )}
      </dl>

      <h3>{t("Why it fired")}</h3>
      <div className="chips">
        {(item.controls_fired || []).map((control) => (
          <code key={control}>{control}</code>
        ))}
        {!item.controls_fired?.length && <span className="muted">—</span>}
      </div>
      {item.blocked_reason && <p className="muted">{item.blocked_reason}</p>}

      {item.entities?.length > 0 && (
        <>
          <h3>{t("Entities")}</h3>
          <table className="compact">
            <thead>
              <tr>
                <th>{t("label")}</th>
                <th>{t("Category")}</th>
                <th>{t("Risk")}</th>
                <th>{t("Source")}</th>
              </tr>
            </thead>
            <tbody>
              {item.entities.map((entity, index) => (
                <tr key={index}>
                  <td>
                    <code>{entity.label}</code> {entity.signature_name && <span className="muted small">({entity.signature_name})</span>}
                  </td>
                  <td>{entity.category}</td>
                  <td>
                    <Badge tone={entity.risk}>{t(entity.risk)}</Badge>
                  </td>
                  <td className="muted">
                    {entity.detected_by} {entity.control && <code>{entity.control}</code>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>{t("Redacted excerpt")}</h3>
      <pre>{item.prompt_excerpt || item.redacted}</pre>
      {audience === "security" && item.redacted && item.redacted !== item.prompt_excerpt && (
        <details>
          <summary className="muted small">raw redacted payload</summary>
          <pre className="small">{item.redacted}</pre>
        </details>
      )}

      <h3>{t("Suggested action")}</h3>
      <p>{t(suggestion)}</p>
      <details>
        <summary>{t("Runbook")}</summary>
        <ol>
          {runbook.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </details>

      <h3>{t("Note")}</h3>
      <textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder={t("Add a note")} />
      <div className="row">
        <select value={item.assignee || ""} onChange={(event) => onPatch({ assignee: event.target.value || null })}>
          <option value="">{t("Unassigned")}</option>
          {admins.map((person) => (
            <option key={person.id} value={person.name}>
              {person.name}
            </option>
          ))}
        </select>
        <button className="btn ghost" onClick={() => onPatch({ note })}>
          {t("Save")}
        </button>
      </div>

      <div className="actions mt">
        {item.status === "open" && (
          <button className="btn ghost" onClick={() => onPatch({ status: "ack" })}>
            {t("Acknowledge")}
          </button>
        )}
        {item.status !== "resolved" && (
          <button className="btn" onClick={() => onPatch({ status: "resolved", note })}>
            {t("Resolve")}
          </button>
        )}
        {item.status !== "false_positive" && (
          <button className="btn ghost" onClick={() => onPatch({ status: "false_positive", note })}>
            {t("Mark false positive")}
          </button>
        )}
        {item.status !== "open" && (
          <button className="btn ghost" onClick={() => onPatch({ status: "open" })}>
            {t("Open")}
          </button>
        )}
        <span className="grow" />
        <button className="btn danger ghost" onClick={onDelete}>
          {t("Delete")}
        </button>
      </div>

      {attempts.length > 0 && (
        <>
          <h3>{t("Recent attempts by this person")}</h3>
          <ul className="timeline">
            {attempts.map((event) => (
              <li key={event.request_id || event.ts}>
                <RelativeTime value={event.ts} /> <Badge tone={event.action}>{t(event.action)}</Badge> <span className="muted">{event.destination}</span>{" "}
                <Labels items={event.labels} max={3} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
