import { useState } from "react";
import { api } from "../api.js";

export default function Agent({ data, refresh }) {
  const people = data.employees || [];
  const [employeeId, setEmployeeId] = useState(people[0]?.id || "emp_anna");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  async function send(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const response = await api.tryAgent(employeeId, text);
      const scan = response.data?.scan || response.data?.error || response.data;
      setResult({
        blocked: response.status === 403 || response.data?.error === "sensitive_data_blocked",
        status: response.status,
        scan: response.data?.scan || null,
        raw: scan,
      });
      refresh();
    } catch (err) {
      setResult({ blocked: false, status: 0, scan: null, raw: String(err.message || err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Czat agenta (przez bramkę)</h1>
      <p className="muted">
        To ten sam kanał co Continue / OpenAI SDK w Antigravity: HTTP na Helios, potem dopiero model.
        Wpisz PESEL — nie wyjdzie.
      </p>
      <form onSubmit={send}>
        <div className="row" style={{ margin: "12px 0" }}>
          <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name} · {person.team}
              </option>
            ))}
          </select>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Skan…" : "Wyślij przez bramkę"}
          </button>
        </div>
        <textarea
          required
          rows={6}
          style={{ width: "100%" }}
          placeholder="np. Maciej Stadler, pesel 44051401359 — napisz maila do HR"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </form>
      {result && (
        <article className={`incident ${result.blocked ? "block" : "resolved"}`} style={{ marginTop: 16 }}>
          <div className="row">
            <strong>{result.blocked ? "Przerwane — nic nie poszło do modelu" : `HTTP ${result.status}`}</strong>
            <span className={`badge ${result.blocked ? "block" : "allow"}`}>
              {result.blocked ? "block" : result.status === 200 ? "allow" : "upstream"}
            </span>
          </div>
          {result.scan && (
            <>
              <p className="muted">{(result.scan.entities || []).map((item) => item.label).join(" · ")}</p>
              <pre>{result.scan.redacted || result.scan.blocked_reason || ""}</pre>
            </>
          )}
          {!result.scan && <pre>{typeof result.raw === "string" ? result.raw : JSON.stringify(result.raw, null, 2)}</pre>}
        </article>
      )}
    </div>
  );
}
