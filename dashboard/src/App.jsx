import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Overview from "./pages/Overview.jsx";
import Incidents from "./pages/Incidents.jsx";
import People from "./pages/People.jsx";
import Roles from "./pages/Roles.jsx";
import Categories from "./pages/Categories.jsx";
import Whitelist from "./pages/Whitelist.jsx";
import Agent from "./pages/Agent.jsx";

const TABS = [
  ["overview", "Przegląd"],
  ["agent", "Czat agenta"],
  ["incidents", "Incydenty"],
  ["people", "Pracownicy"],
  ["roles", "Role"],
  ["categories", "Kategorie"],
  ["whitelist", "Whitelist"],
];

export default function App() {
  const [tab, setTab] = useState("overview");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [seenOpen, setSeenOpen] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setData(await api.workspace());
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [refresh]);

  const openCount = data?.stats?.open_incidents ?? 0;
  useEffect(() => {
    if (seenOpen === null && data) {
      setSeenOpen(openCount);
      return;
    }
    if (data && seenOpen !== null && openCount > seenOpen) {
      const newest = (data.incidents || []).find((item) => item.status === "open");
      setToast(
        newest
          ? `${newest.employee_name} odjebał na ${newest.destination}: ${newest.labels.join(", ")}`
          : "Nowy incydent"
      );
      setSeenOpen(openCount);
      window.setTimeout(() => setToast(""), 6000);
    }
  }, [openCount, data, seenOpen]);

  const props = { data, refresh };

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">
          Helios <span>Guard</span>
        </div>
        <p>Dashboard managera · Laya</p>
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {label}
            {id === "incidents" && openCount ? ` (${openCount})` : ""}
          </button>
        ))}
      </aside>
      <main className="main">
        {error && <p className="muted">API: {error}. Uruchom <code>python -m sensitive_guard serve</code>.</p>}
        {!data && <p className="muted">Ładowanie workspace…</p>}
        {data && tab === "overview" && <Overview {...props} />}
        {data && tab === "agent" && <Agent {...props} />}
        {data && tab === "incidents" && <Incidents {...props} />}
        {data && tab === "people" && <People {...props} />}
        {data && tab === "roles" && <Roles {...props} />}
        {data && tab === "categories" && <Categories {...props} />}
        {data && tab === "whitelist" && <Whitelist {...props} />}
      </main>
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
