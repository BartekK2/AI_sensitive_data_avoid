import { useRef, useState } from "react";
import { api } from "../api.js";
import { Badge, Section, useConfirm } from "../components/ui.jsx";
import { useApp } from "../store.jsx";

const EMPTY = { label: "", risk: "medium", enabled: true, min_confidence: 0.35 };

function categoryKey(name) {
  const key = name
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/ł/g, "l")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
  return key || "topic";
}

export default function Categories() {
  const { t, data, refresh } = useApp();
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saveError, setSaveError] = useState("");
  const [draftConfidence, setDraftConfidence] = useState({});
  const confidenceTimers = useRef({});
  const [ask, confirmEl] = useConfirm();
  if (!data) return <p className="muted">{t("Loading")}…</p>;

  async function submit(event) {
    event.preventDefault();
    const name = form.label.trim();
    if (!name) return;
    const existing = editingId ? data.categories.find((item) => item.id === editingId) : null;
    const { patterns: _ignored, ...kept } = existing || {};
    try {
      await api.saveCategory({
        ...kept,
        label: name,
        key: existing?.key || categoryKey(name),
        risk: form.risk,
        enabled: form.enabled,
        min_confidence: form.min_confidence,
        builtin: existing?.builtin || false,
        id: editingId || undefined,
      });
    } catch (err) {
      setSaveError(String(err.message || err));
      return;
    }
    setSaveError("");
    setForm(EMPTY);
    setEditingId(null);
    refresh();
  }

  async function toggle(item) {
    if (item.enabled && item.risk === "critical") {
      const ok = await ask({ title: t("Disable"), body: t("Disabling this control lets {what} through. Continue?", { what: item.label }), confirmLabel: t("Disable") });
      if (!ok) return;
    }
    const { patterns: _patterns, ...kept } = item;
    await api.saveCategory({ ...kept, enabled: !item.enabled });
    refresh();
  }

  function queueConfidence(item, value) {
    setDraftConfidence((current) => ({ ...current, [item.id]: value }));
    window.clearTimeout(confidenceTimers.current[item.id]);
    confidenceTimers.current[item.id] = window.setTimeout(() => saveConfidence(item, value), 250);
  }

  async function saveConfidence(item, value) {
    const { patterns: _patterns, ...kept } = item;
    try {
      await api.saveCategory({ ...kept, min_confidence: value });
      setSaveError("");
      refresh();
    } catch (err) {
      setSaveError(String(err.message || err));
    }
  }

  function edit(item) {
    setEditingId(item.id);
    setSaveError("");
    setForm({ label: item.label, risk: item.risk, enabled: item.enabled, min_confidence: item.min_confidence ?? 0.35 });
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>{t("Categories")}</h1>
          <p className="lead">{t("A disabled category does not block and does not create an incident.")}</p>
        </div>
      </div>

      <Section title={editingId ? `${t("Edit")}: ${form.label}` : t("Add category")}>
        <form className="grid" onSubmit={submit}>
          <input required placeholder={t("Category")} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          {!editingId || !data.categories.find((item) => item.id === editingId)?.builtin ? (
            <label className="check">
              {t("Minimum confidence")}
              <input
                type="range"
                min="0.05"
                max="0.95"
                step="0.05"
                value={form.min_confidence}
                onChange={(event) => setForm({ ...form, min_confidence: Number(event.target.value) })}
              />
              <b>{Number(form.min_confidence).toFixed(2)}</b>
              <span className="muted small">{t("Lower also catches related words.")}</span>
            </label>
          ) : null}
          <select value={form.risk} onChange={(e) => setForm({ ...form, risk: e.target.value })}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
          <div className="actions">
            <button className="btn" type="submit">
              {editingId ? t("Save") : t("Add category")}
            </button>
            {editingId && (
              <button className="btn ghost" type="button" onClick={() => { setEditingId(null); setForm(EMPTY); setSaveError(""); }}>
                {t("Cancel")}
              </button>
            )}
          </div>
          {saveError && <p className="lead">{saveError}</p>}
        </form>
      </Section>

      <table>
        <thead>
          <tr>
            <th>{t("Category")}</th>
            <th>{t("Risk")}</th>
            <th>{t("Minimum confidence")}</th>
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
              <td>
                {item.builtin ? (
                  <span className="muted">—</span>
                ) : (
                  <label className="check">
                    <input
                      type="range"
                      min="0.05"
                      max="0.95"
                      step="0.05"
                      value={draftConfidence[item.id] ?? item.min_confidence ?? 0.35}
                      onChange={(event) => queueConfidence(item, Number(event.target.value))}
                      aria-label={t("Minimum confidence")}
                    />
                    <b>{Number(draftConfidence[item.id] ?? item.min_confidence ?? 0.35).toFixed(2)}</b>
                  </label>
                )}
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
