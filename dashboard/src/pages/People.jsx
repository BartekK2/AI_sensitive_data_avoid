import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Badge, Empty, RelativeTime, Section, Select, useConfirm } from "../components/ui.jsx";
import { hrefFor } from "../router.js";
import { useApp } from "../store.jsx";

const EMPTY = { name: "", email: "", team: "", role_id: "" };

export default function People() {
  const { t, data, refresh, route, metrics } = useApp();
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [team, setTeam] = useState("");
  const [query, setQuery] = useState("");
  const [ask, confirmEl] = useConfirm();

  const roles = Object.fromEntries(data.roles.map((role) => [role.id, role]));
  const teams = [...new Set(data.employees.map((item) => item.team).filter(Boolean))].sort();

  const stats = useMemo(() => {
    const out = {};
    for (const incident of data.incidents || []) {
      const key = incident.employee_id || "__unknown__";
      const entry = (out[key] ||= { open: 0, total: 0, critical: 0, last: null, blocked: 0 });
      entry.total += incident.count || 1;
      if (incident.status === "open" || !incident.status) entry.open += 1;
      if (incident.risk === "critical") entry.critical += 1;
      if (incident.action === "block") entry.blocked += 1;
      if (!entry.last || incident.created_at > entry.last) entry.last = incident.created_at;
    }
    return out;
  }, [data.incidents]);

  const unknown = stats.__unknown__;

  useEffect(() => {
    if (route.params.id) {
      const person = data.employees.find((item) => item.id === route.params.id);
      if (person) startEdit(person);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.params.id]);

  function startEdit(person) {
    setEditingId(person.id);
    setForm({ name: person.name, email: person.email || "", team: person.team || "", role_id: person.role_id || "" });
  }

  async function submit(event) {
    event.preventDefault();
    await api.saveEmployee(editingId ? { ...form, id: editingId } : form);
    setForm(EMPTY);
    setEditingId(null);
    refresh();
  }

  const rows = data.employees
    .filter((item) => !team || item.team === team)
    .filter((item) => !query || `${item.name} ${item.email} ${item.team}`.toLowerCase().includes(query.toLowerCase()))
    .map((item) => ({ ...item, stats: stats[item.id] || { open: 0, total: 0, critical: 0, last: null, blocked: 0 } }))
    .sort((a, b) => b.stats.open - a.stats.open || b.stats.total - a.stats.total || a.name.localeCompare(b.name));

  const budgetRows = Object.fromEntries((metrics?.top_people || []).map((row) => [row.employee_id || row.id, row]));

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("People")}</h1>
          <p className="lead">{t("Who sends what. The extension and the agent identify people by employee ID or e-mail.")}</p>
        </div>
      </div>

      {unknown && (
        <div className="banner warn">
          <b>{t("Unknown actors")}</b>: {unknown.total} {t("Incidents").toLowerCase()} ({unknown.open} {t("open")}) —{" "}
          <a className="link" href={hrefFor("incidents", { employee: "unknown" })}>
            {t("Show")}
          </a>
          . {t("Set employeeId in the extension or send X-Employee-Id from the agent.")}
        </div>
      )}

      <Section title={editingId ? `${t("Edit")}: ${form.name}` : t("Add person")}>
        <form className="grid" onSubmit={submit}>
          <input required placeholder={t("Name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="e-mail" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input placeholder={t("Team")} value={form.team} onChange={(e) => setForm({ ...form, team: e.target.value })} list="teams" />
          <datalist id="teams">
            {teams.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <select value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
            <option value="">{t("Role")}…</option>
            {data.roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
          <div className="actions">
            <button className="btn" type="submit">
              {editingId ? t("Save") : t("Add person")}
            </button>
            {editingId && (
              <button className="btn ghost" type="button" onClick={() => { setEditingId(null); setForm(EMPTY); }}>
                {t("Cancel")}
              </button>
            )}
          </div>
        </form>
      </Section>

      <div className="toolbar">
        <input placeholder={t("Search")} value={query} onChange={(event) => setQuery(event.target.value)} />
        <Select value={team} onChange={setTeam} placeholder={t("All teams")} options={teams.map((name) => [name, name])} />
        <span className="muted small">{rows.length}</span>
      </div>

      {!rows.length && <Empty />}
      <table>
        <thead>
          <tr>
            <th>{t("Name")}</th>
            <th>{t("Team")}</th>
            <th>{t("Role")}</th>
            <th>{t("Open")}</th>
            <th>{t("Incidents")}</th>
            <th>{t("Last attempt")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((person) => (
            <tr key={person.id} className={`person-row ${route.params.id === person.id ? "highlight" : ""} ${person.stats.critical ? "has-critical" : ""}`}>
              <td>
                <strong>{person.name}</strong>
                <div className="muted small">
                  {person.email} · <code>{person.id}</code>
                </div>
              </td>
              <td>{person.team}</td>
              <td>
                {roles[person.role_id] ? (
                  <a className="link" href={hrefFor("roles", { id: person.role_id })}>
                    {roles[person.role_id].name}
                  </a>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>
                {person.stats.open ? <Badge tone={person.stats.critical ? "critical" : "high"}>{person.stats.open}</Badge> : <span className="muted">0</span>}
              </td>
              <td>
                <a className="link" href={hrefFor("incidents", { employee: person.id })}>
                  {person.stats.total}
                </a>
                {person.stats.blocked > 0 && <span className="muted small"> · {person.stats.blocked} {t("blocked")}</span>}
                {budgetRows[person.id]?.tokens ? <span className="muted small"> · {budgetRows[person.id].tokens} tok</span> : null}
              </td>
              <td className="muted small">
                <RelativeTime value={person.stats.last} />
              </td>
              <td className="actions">
                <button className="btn ghost" onClick={() => startEdit(person)}>
                  {t("Edit")}
                </button>
                <button
                  className="btn danger ghost"
                  onClick={async () => {
                    if (await ask({ title: `${t("Delete")} ${person.name}?`, body: t("Incidents stay in the queue with the employee ID.") })) {
                      await api.deleteEmployee(person.id);
                      refresh();
                    }
                  }}
                >
                  {t("Delete")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {confirmEl}
    </div>
  );
}
