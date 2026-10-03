import { useState } from "react";
import { api } from "../api.js";
import { Badge, Banner, Section, useConfirm } from "../components/ui.jsx";
import { useApp } from "../store.jsx";

const EMPTY = { key: "", label: "", risk: "medium", enabled: true, patterns: "" };

export default function Categories() {
  const { t, data, refresh } = useApp();
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [ask, confirmEl] = useConfirm();

  async function submit(event) {
    event.preventDefault();
    const patterns = form.patterns
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const existing = editingId ? data.categories.find((item) => item.id === editingId) : null;
    await api.saveCategory({ ...(existing || {}), ...form, patterns, builtin: existing?.builtin || false, id: editingId || undefined });
    setForm(EMPTY);
    setEditingId(null);
    refresh();
  }

  async function toggle(item) {
    if (item.enabled && item.risk === "critical") {
      const ok = await ask({ title: t("Disable"), body: t("Disabling this control lets {what} through. Continue?", { what: item.label }), confirmLabel: t("Disable") });
      if (!ok) return;
    }
    await api.saveCategory({ ...item, enabled: !item.enabled });
    refresh();
  }

  function edit(item) {
    setEditingId(item.id);
    setForm({ key: item.key, label: item.label, risk: item.risk, enabled: item.enabled, patterns: (item.patterns || []).join("\n") });
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Categories")}</h1>
          <p className="lead">{t("A disabled category does not block and does not create an incident.")}</p>
        </div>
      </div>

      <Banner tone="warn">{t("A category without a detector finds nothing. Add regex patterns to make it real.")}</Banner>

      <Section title={editingId ? `${t("Edit")}: ${form.label}` : t("Add category")}>
        <form className="grid" onSubmit={submit}>
          <input required placeholder="key (e.g. health)" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} disabled={Boolean(editingId)} />
          <input required placeholder={t("label")} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          <select value={form.risk} onChange={(e) => setForm({ ...form, risk: e.target.value })}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
          <textarea
            className="span-all mono"
            rows={3}
            placeholder={`${t("Patterns")} (regex, one per line)\n\\b(diabetes|HIV|cancer)\\b\nPROJECT-[A-Z]{3}-\\d{3}`}
            value={form.patterns}
            onChange={(e) => setForm({ ...form, patterns: e.target.value })}
          />
          <div className="actions">
            <button className="btn" type="submit">
              {editingId ? t("Save") : t("Add category")}
            </button>
            {editingId && (
              <button className="btn ghost" type="button" onClick={() => { setEditingId(null); setForm(EMPTY); }}>
                {t("Cancel")}
              </button>
            )}
          </div>
        </form>
      </Section>

      <table>
        <thead>
          <tr>
            <th>{t("Category")}</th>
            <th>{t("Risk")}</th>
            <th>{t("Patterns")}</th>
            <th>{t("Status")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.categories.map((item) => (
            <tr key={item.id} className={item.enabled ? "" : "disabled"}>
              <td>
                <strong>{item.label}</strong>
                <div className="muted small">
                  <code>{item.key}</code> {item.builtin ? <span className="muted">builtin</span> : null}
                </div>
              </td>
              <td>
                <Badge tone={item.risk}>{t(item.risk)}</Badge>
              </td>
              <td className="small">
                {item.builtin && !item.patterns?.length && <span className="muted">finder + classifier</span>}
                {(item.patterns || []).map((pattern) => (
                  <div key={pattern}>
                    <code>{pattern}</code>
                  </div>
                ))}
                {!item.builtin && !item.patterns?.length && <span className="danger">{t("Patterns")}: 0</span>}
              </td>
              <td>{item.enabled ? t("Enabled") : t("Disabled")}</td>
              <td className="actions">
                <button className="btn ghost" onClick={() => toggle(item)}>
                  {item.enabled ? t("Disable") : t("Enable")}
                </button>
                <button className="btn ghost" onClick={() => edit(item)}>
                  {t("Edit")}
                </button>
                {!item.builtin && (
                  <button
                    className="btn danger ghost"
                    onClick={async () => {
                      if (await ask({ title: `${t("Delete")} ${item.label}?` })) {
                        await api.deleteCategory(item.id);
                        refresh();
                      }
                    }}
                  >
                    {t("Delete")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {confirmEl}
    </div>
  );
}
