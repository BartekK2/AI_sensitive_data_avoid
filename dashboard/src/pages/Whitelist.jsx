import { useState } from "react";
import { api } from "../api.js";
import { Badge, Section, useConfirm } from "../components/ui.jsx";
import { useApp } from "../store.jsx";

const EMPTY = { type: "domain", value: "", reason: "", enabled: true };
const EXAMPLES = { domain: "helios.pl", email: "pomoc@helios.pl", pattern: "5252341111", label: "person name / contact" };

export default function Whitelist() {
  const { t, data, refresh } = useApp();
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [ask, confirmEl] = useConfirm();

  async function submit(event) {
    event.preventDefault();
    await api.saveWhitelist(editingId ? { ...form, id: editingId } : form);
    setForm(EMPTY);
    setEditingId(null);
    refresh();
  }

  async function toggle(item) {
    await api.saveWhitelist({ ...item, enabled: !item.enabled });
    refresh();
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Whitelist")}</h1>
          <p className="lead">{t("Domain, e-mail, pattern or label that is not treated as a leak.")}</p>
        </div>
      </div>

      <Section title={editingId ? t("Edit") : t("Add exception")}>
        <form className="grid" onSubmit={submit}>
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {Object.keys(EXAMPLES).map((type) => (
              <option key={type} value={type}>
                {t(type)}
              </option>
            ))}
          </select>
          <input required placeholder={EXAMPLES[form.type]} value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
          <input placeholder={t("Reason")} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          <div className="actions">
            <button className="btn" type="submit">
              {editingId ? t("Save") : t("Add exception")}
            </button>
            {editingId && (
              <button className="btn ghost" type="button" onClick={() => { setEditingId(null); setForm(EMPTY); }}>
                {t("Cancel")}
              </button>
            )}
          </div>
        </form>
        <p className="muted small">
          {Object.entries(EXAMPLES).map(([type, example]) => (
            <span key={type} className="mr">
              <b>{t(type)}</b>: <code>{example}</code>
            </span>
          ))}
        </p>
      </Section>

      <table>
        <thead>
          <tr>
            <th>{t("Type")}</th>
            <th>{t("Value")}</th>
            <th>{t("Reason")}</th>
            <th>{t("Status")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.whitelist.map((item) => (
            <tr key={item.id} className={item.enabled === false ? "disabled" : ""}>
              <td>
                <Badge tone="neutral">{t(item.type)}</Badge>
              </td>
              <td>
                <code>{item.value}</code>
              </td>
              <td className="muted">{item.reason}</td>
              <td>
                <label className="switch">
                  <input type="checkbox" checked={item.enabled !== false} onChange={() => toggle(item)} />
                  <span />
                </label>
              </td>
              <td className="actions">
                <button className="btn ghost" onClick={() => { setEditingId(item.id); setForm({ type: item.type, value: item.value, reason: item.reason || "", enabled: item.enabled !== false }); }}>
                  {t("Edit")}
                </button>
                <button
                  className="btn danger ghost"
                  onClick={async () => {
                    if (await ask({ title: `${t("Delete")} ${item.value}?` })) {
                      await api.deleteWhitelist(item.id);
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
