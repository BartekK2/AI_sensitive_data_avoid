import { useState } from "react";
import { api } from "../api.js";

export default function Roles({ data, refresh }) {
  const keys = data.categories.map((item) => item.key);
  const [form, setForm] = useState({
    name: "",
    level: "standard",
    description: "",
    allowed_categories: [],
    can_override: false,
  });

  async function add(event) {
    event.preventDefault();
    await api.saveRole(form);
    setForm({ name: "", level: "standard", description: "", allowed_categories: [], can_override: false });
    refresh();
  }

  function toggle(key) {
    const has = form.allowed_categories.includes(key);
    setForm({
      ...form,
      allowed_categories: has ? form.allowed_categories.filter((item) => item !== key) : [...form.allowed_categories, key],
    });
  }

  return (
    <div>
      <h1>Role</h1>
      <p className="muted">Kategorie na roli nie generują incydentu (np. HR może wysyłać imiona i telefony).</p>
      <form className="grid" onSubmit={add}>
        <input required placeholder="Nazwa roli" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
          <option value="standard">standard</option>
          <option value="elevated">elevated</option>
          <option value="admin">admin</option>
        </select>
        <input
          placeholder="Opis"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <label>
          <input
            type="checkbox"
            checked={form.can_override}
            onChange={(e) => setForm({ ...form, can_override: e.target.checked })}
          />{" "}
          może nadpisać blokadę
        </label>
        <div>
          {keys.map((key) => (
            <label key={key} style={{ marginRight: 10 }}>
              <input type="checkbox" checked={form.allowed_categories.includes(key)} onChange={() => toggle(key)} /> {key}
            </label>
          ))}
          <label>
            <input type="checkbox" checked={form.allowed_categories.includes("*")} onChange={() => toggle("*")} /> wszystkie
          </label>
        </div>
        <button className="btn" type="submit">
          Dodaj rolę
        </button>
      </form>
      {data.roles.map((role) => (
        <div className="panel" key={role.id} style={{ marginBottom: 12 }}>
          <div className="row">
            <h3>{role.name}</h3>
            <span className="badge medium">{role.level}</span>
            <button className="btn danger" onClick={() => api.deleteRole(role.id).then(refresh)}>
              Usuń
            </button>
          </div>
          <p className="muted">{role.description}</p>
          <p>Wyjątki: {(role.allowed_categories || []).join(", ") || "brak"}</p>
        </div>
      ))}
    </div>
  );
}
