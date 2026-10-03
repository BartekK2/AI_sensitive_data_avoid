import { useState } from "react";
import { api } from "../api.js";

export default function Categories({ data, refresh }) {
  const [form, setForm] = useState({ key: "", label: "", risk: "medium", enabled: true });

  async function add(event) {
    event.preventDefault();
    await api.saveCategory({ ...form, builtin: false });
    setForm({ key: "", label: "", risk: "medium", enabled: true });
    refresh();
  }

  async function toggle(item) {
    await api.saveCategory({ ...item, enabled: !item.enabled });
    refresh();
  }

  return (
    <div>
      <h1>Kategorie</h1>
      <p className="muted">Wyłączona kategoria nie blokuje i nie robi incydentu.</p>
      <form className="grid" onSubmit={add}>
        <input required placeholder="klucz (np. health)" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} />
        <input required placeholder="Etykieta" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        <select value={form.risk} onChange={(e) => setForm({ ...form, risk: e.target.value })}>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
        <button className="btn" type="submit">
          Dodaj kategorię
        </button>
      </form>
      <table>
        <thead>
          <tr>
            <th>Kategoria</th>
            <th>Ryzyko</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.categories.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{item.label}</strong>
                <div className="muted">{item.key}</div>
              </td>
              <td>
                <span className={`badge ${item.risk}`}>{item.risk}</span>
              </td>
              <td>{item.enabled ? "włączona" : "wyłączona"}</td>
              <td className="actions">
                <button className="btn ghost" onClick={() => toggle(item)}>
                  {item.enabled ? "Wyłącz" : "Włącz"}
                </button>
                {!item.builtin && (
                  <button className="btn danger" onClick={() => api.deleteCategory(item.id).then(refresh)}>
                    Usuń
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
