export default function Overview({ data }) {
  const open = [...(data.incidents || [])].reverse().filter((item) => item.status === "open");
  const byTeam = {};
  for (const item of data.incidents || []) {
    byTeam[item.team] = (byTeam[item.team] || 0) + 1;
  }
  return (
    <div>
      <h1>Ktoś odjebał — widok operacyjny</h1>
      <p className="muted">Alerty z warstwy Laya, zanim tekst wyleci do ChatGPT / Claude / Gemini.</p>
      <div className="cards">
        <div className="card">
          Otwarte incydenty
          <b>{data.stats.open_incidents}</b>
        </div>
        <div className="card">
          Pracownicy
          <b>{data.stats.employees}</b>
        </div>
        <div className="card">
          Role
          <b>{data.stats.roles}</b>
        </div>
        <div className="card">
          Whitelist
          <b>{data.stats.whitelist}</b>
        </div>
      </div>
      <h2>Najnowsze zgłoszenia</h2>
      {open.slice(0, 5).map((item) => (
        <article key={item.id} className={`incident ${item.action}`}>
          <div className="row">
            <strong>{item.employee_name}</strong>
            <span className={`badge ${item.risk}`}>{item.risk}</span>
            <span className={`badge ${item.action}`}>{item.action}</span>
            <span className="muted">{item.destination}</span>
          </div>
          <p className="muted">
            {item.team} · {item.role_name} · {(item.labels || []).join(", ")}
          </p>
          <pre>{item.redacted}</pre>
        </article>
      ))}
      {!open.length && <p className="muted">Spokój na razie. Żaden otwarty incydent.</p>}
    </div>
  );
}
