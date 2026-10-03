import { useState } from "react";
import { api } from "../api.js";

export default function People({ data, refresh }) {
  const [form, setForm] = useState({
    name: "",
    email: "",
    team: "Support",
    role_id: data.roles[0]?.id || "",
  });

  function roleName(id) {
    return data.roles.find((role) => role.id === id)?.name || id;
  }

  async function add(event) {
    event.preventDefault();
    await api.saveEmployee(form);
    setForm({ ...form, name: "", email: "" });
    refresh();
  }

  async function assign(employee, role_id) {
    await api.saveEmployee({ ...employee, role_id });
    refresh();
  }

  return (
    <div>
      <h1>Pracownicy i role</h1>
      <form className="grid" onSubmit={add}>
        <input
          required
          placeholder="Imię i nazwisko"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          required
          type="email"
          placeholder="e-mail"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <input placeholder="Zespół" value={form.team} onChange={(e) => setForm({ ...form, team: e.target.value })} />
        <select value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
          {data.roles.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
        <button className="btn" type="submit">
          Dodaj
        </button>
      </form>
      <table>
        <thead>
          <tr>
            <th>Osoba</th>
            <th>Zespół</th>
            <th>Rola</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.employees.map((employee) => (
            <tr key={employee.id}>
              <td>
                <strong>{employee.name}</strong>
                <div className="muted">{employee.email}</div>
              </td>
              <td>{employee.team}</td>
              <td>
                <select value={employee.role_id} onChange={(e) => assign(employee, e.target.value)}>
                  {data.roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <button className="btn danger" onClick={() => api.deleteEmployee(employee.id).then(refresh)}>
                  Usuń
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Aktualna mapa: {data.employees.map((e) => `${e.name} → ${roleName(e.role_id)}`).join(" · ")}</p>
    </div>
  );
}
