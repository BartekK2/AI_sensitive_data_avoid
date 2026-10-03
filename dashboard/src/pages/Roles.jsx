import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge, Section, useConfirm } from "../components/ui.jsx";
import { useApp } from "../store.jsx";

const EMPTY = { name: "", level: "standard", description: "", allowed_categories: [], can_override: false };
const SAMPLE = "Jan Kowalski, tel +48 600 100 200, mail jan@example.com, PESEL 44051401359, IBAN PL61109010140000071219812874";

export default function Roles() {
  const { t, data, refresh, route } = useApp();
  const keys = data.categories.map((item) => item.key);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [sample, setSample] = useState(SAMPLE);
  const [preview, setPreview] = useState({});
  const [ask, confirmEl] = useConfirm();

  useEffect(() => {
    if (route.params.id) {
      const role = data.roles.find((item) => item.id === route.params.id);
      if (role) startEdit(role);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.params.id]);

  function startEdit(role) {
    setEditingId(role.id);
    setForm({ ...EMPTY, ...role });
  }

  async function submit(event) {
    event.preventDefault();
    await api.saveRole(editingId ? { ...form, id: editingId } : form);
    setForm(EMPTY);
    setEditingId(null);
    refresh();
  }

  function toggle(key) {
    const has = form.allowed_categories.includes(key);
    setForm({
      ...form,
      allowed_categories: has ? form.allowed_categories.filter((item) => item !== key) : [...form.allowed_categories, key],
    });
  }

  async function previewRole(role) {
    const person = data.employees.find((item) => item.role_id === role.id);
    const scan = await api.scan({ text: sample, employee_id: person?.id, destination: "preview" });
    setPreview((current) => ({ ...current, [role.id]: { scan, person } }));
  }

  async function remove(role) {
    const users = data.employees.filter((item) => item.role_id === role.id).length;
    const ok = await ask({ title: `${t("Delete")} ${role.name}?`, body: users ? `${users} ${t("People").toLowerCase()} → ${t("Role")} ∅` : t("This cannot be undone.") });
    if (ok) {
      await api.deleteRole(role.id);
      refresh();
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Roles")}</h1>
          <p className="lead">{t("Exceptions on a role do not generate incidents (e.g. HR may send names and phones).")}</p>
        </div>
      </div>

      <Section title={editingId ? `${t("Edit")}: ${form.name}` : t("Add role")}>
        <form className="grid" onSubmit={submit}>
          <input required placeholder={t("Role name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
            <option value="standard">standard</option>
            <option value="elevated">elevated</option>
            <option value="admin">admin</option>
          </select>
          <input placeholder={t("Description")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <label className="check">
            <input type="checkbox" checked={form.can_override} onChange={(e) => setForm({ ...form, can_override: e.target.checked })} /> {t("can override blocks")}
          </label>
          <div className="chips span-all">
            {keys.map((key) => (
              <label key={key} className={`chip ${form.allowed_categories.includes(key) ? "ok" : ""}`}>
                <input type="checkbox" checked={form.allowed_categories.includes(key)} onChange={() => toggle(key)} /> {key}
              </label>
            ))}
            <label className={`chip ${form.allowed_categories.includes("*") ? "ok" : ""}`}>
              <input type="checkbox" checked={form.allowed_categories.includes("*")} onChange={() => toggle("*")} /> {t("all")}
            </label>
          </div>
          <div className="actions">
            <button className="btn" type="submit">
              {editingId ? t("Save") : t("Add role")}
            </button>
            {editingId && (
              <button className="btn ghost" type="button" onClick={() => { setEditingId(null); setForm(EMPTY); }}>
                {t("Cancel")}
              </button>
            )}
          </div>
        </form>
      </Section>

      <Section title={t("What can this role send?")} aside={<input className="grow" value={sample} onChange={(e) => setSample(e.target.value)} />}>
        <p className="muted small">{t("Sample text")}: {t("Changes apply on the next request. No restart needed.")}</p>
      </Section>

      {data.roles.map((role) => {
        const users = data.employees.filter((item) => item.role_id === role.id);
        const pv = preview[role.id];
        return (
          <div className="panel mb" key={role.id}>
            <div className="row">
              <h3>{role.name}</h3>
              <Badge tone={role.level === "admin" ? "critical" : role.level === "elevated" ? "medium" : "neutral"}>{role.level}</Badge>
              {role.can_override && <Badge tone="warn">{t("can override blocks")}</Badge>}
              <span className="muted small">{users.length} {t("People").toLowerCase()}</span>
              <span className="grow" />
              <button className="btn ghost" onClick={() => previewRole(role)}>
                {t("What can this role send?")}
              </button>
              <button className="btn ghost" onClick={() => startEdit(role)}>
                {t("Edit")}
              </button>
              <button className="btn danger ghost" onClick={() => remove(role)}>
                {t("Delete")}
              </button>
            </div>
            <p className="muted">{role.description}</p>
            <p>
              {t("Exceptions")}: {(role.allowed_categories || []).length ? (role.allowed_categories || []).map((key) => <code key={key}>{key}</code>) : <span className="muted">—</span>}
            </p>
            {pv && (
              <div className={`incident ${pv.scan.action} compact`}>
                <div className="row">
                  <Badge tone={pv.scan.action}>{t(pv.scan.action)}</Badge>
                  <Badge tone={pv.scan.risk}>{t(pv.scan.risk)}</Badge>
                  <span className="muted small">
                    {pv.person ? pv.person.name : t("Unknown actors")} · {(pv.scan.skipped || []).filter((item) => item.skipped_by === "role").length} {t("Exceptions").toLowerCase()}
                  </span>
                </div>
                <pre>{pv.scan.redacted}</pre>
              </div>
            )}
          </div>
        );
      })}
      {confirmEl}
    </div>
  );
}
