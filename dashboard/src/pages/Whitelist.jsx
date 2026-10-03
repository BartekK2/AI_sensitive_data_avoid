import { useState } from "react";
import { api } from "../api.js";

export default function Whitelist({ data, refresh }) {
  const [form, setForm] = useState({ type: "domain", value: "", reason: "", enabled: true });

  async function add(event) {
    event.preventDefault();
    await api.saveWhitelist(form);
    setForm({ type: "domain", value: "", reason: "", enabled: true });
    refresh();
  }

  return (
    <div>
      <h1>Whitelist</h1>
      <p className="muted">Domena, e-mail, wzorzec albo etykieta Laya, której nie traktujemy jako wycieku.</p>
      <form className="grid" onSubmit={add}>
        <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
          <option value="domain">domena</option>
          <option value="email">e-mail</option>
          <option value="pattern">wzorzec</option>
          <option value="label">etykieta / kategoria</option>
        </select>
        <input required placeholder="helios.pl / pomoc@… / PESEL testowy" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
        <input placeholder="Powód" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        <button className="btn" type="submit">
          Dodaj wyjątek
        </button>
      </form>
      <table>
        <thead>
          <tr>
            <th>Typ</th>
            <th>Wartość</th>
            <th>Powód</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.whitelist.map((item) => (
            <tr key={item.id}>
              <td>{item.type}</td>
              <td>
                <code>{item.value}</code>
              </td>
              <td className="muted">{item.reason}</td>
              <td>
                <button className="btn danger" onClick={() => api.deleteWhitelist(item.id).then(refresh)}>
                  Usuń
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
