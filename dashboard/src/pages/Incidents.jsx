import { api } from "../api.js";

export default function Incidents({ data, refresh }) {
  async function setStatus(item, status) {
    await api.patchIncident(item.id, { status });
    refresh();
  }

  const items = [...(data.incidents || [])].reverse();

  return (
    <div>
      <h1>Incydenty</h1>
      <p className="muted">Każda zablokowana albo zredagowana wysyłka ląduje tutaj z rolą i zespołem.</p>
      {items.map((item) => (
        <article key={item.id} className={`incident ${item.action} ${item.status}`}>
          <div className="row">
            <strong>{item.employee_name}</strong>
            <span className={`badge ${item.status}`}>{item.status}</span>
            <span className={`badge ${item.risk}`}>{item.risk}</span>
            <span className="muted">{item.created_at}</span>
          </div>
          <p>
            {item.team} · {item.role_name} · {item.destination}
          </p>
          <p className="muted">{(item.labels || []).join(" · ")}</p>
          <pre>{item.redacted}</pre>
          {item.note && <p>{item.note}</p>}
          <div className="actions">
            {item.status === "open" && (
              <button className="btn ghost" onClick={() => setStatus(item, "ack")}>
                Przyjąłem
              </button>
            )}
            {item.status !== "resolved" && (
              <button className="btn" onClick={() => setStatus(item, "resolved")}>
                Zamknij
              </button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
