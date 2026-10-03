import { Banner, Toasts } from "./components/ui.jsx";
import { hrefFor } from "./router.js";
import { useApp } from "./store.jsx";
import Posture from "./pages/Posture.jsx";
import Incidents from "./pages/Incidents.jsx";
import Controls from "./pages/Controls.jsx";
import Policy from "./pages/Policy.jsx";
import Budget from "./pages/Budget.jsx";
import Threats from "./pages/Threats.jsx";
import People from "./pages/People.jsx";
import Roles from "./pages/Roles.jsx";
import Categories from "./pages/Categories.jsx";
import Whitelist from "./pages/Whitelist.jsx";
import Agent from "./pages/Agent.jsx";
import Audit from "./pages/Audit.jsx";
import Telemetry from "./pages/Telemetry.jsx";
import Architecture from "./pages/Architecture.jsx";

const PAGES = {
  posture: Posture,
  overview: Posture,
  incidents: Incidents,
  controls: Controls,
  policy: Policy,
  budget: Budget,
  threats: Threats,
  people: People,
  roles: Roles,
  categories: Categories,
  whitelist: Whitelist,
  agent: Agent,
  audit: Audit,
  telemetry: Telemetry,
  architecture: Architecture,
};

const NAV = [
  { group: "Monitor", items: [
    ["posture", "Security posture", "both"],
    ["incidents", "Incidents", "both"],
    ["threats", "Threats", "security"],
    ["audit", "Audit", "security"],
    ["telemetry", "Telemetry", "security"],
  ] },
  { group: "Govern", items: [
    ["controls", "Controls", "both"],
    ["policy", "Policy", "both"],
    ["budget", "Budget", "both"],
    ["roles", "Roles", "both"],
    ["categories", "Categories", "both"],
    ["whitelist", "Whitelist", "both"],
    ["people", "People", "both"],
  ] },
  { group: "Demo", items: [
    ["agent", "Agent chat", "both"],
    ["architecture", "Architecture", "both"],
  ] },
];

export default function App() {
  const { t, lang, setLang, audience, setAudience, route, data, metrics, health, error, policyBanner } = useApp();
  const Page = PAGES[route.page] || Posture;
  const openCount = data?.stats?.open_incidents ?? 0;
  const criticalCount = data?.stats?.open_critical ?? 0;
  const score = metrics?.posture?.score;

  return (
    <div className={`app audience-${audience}`}>
      <aside className="nav">
        <div className="brand">
          Helios <span>Guard</span>
        </div>
        <p className="muted small">{t("AI control layer")} · {health?.backend || "…"}</p>

        <div className="segmented" role="tablist">
          <button className={audience === "manager" ? "active" : ""} onClick={() => setAudience("manager")}>
            {t("Manager")}
          </button>
          <button className={audience === "security" ? "active" : ""} onClick={() => setAudience("security")}>
            {t("Security")}
          </button>
        </div>

        {NAV.map((group) => {
          const items = group.items.filter(([, , who]) => who === "both" || who === audience);
          if (!items.length) return null;
          return (
            <div key={group.group} className="nav-group">
              <div className="nav-group-title">{t(group.group)}</div>
              {items.map(([id, label]) => (
                <a key={id} href={hrefFor(id)} className={route.page === id || (id === "posture" && route.page === "overview") ? "active" : ""}>
                  {t(label)}
                  {id === "incidents" && openCount ? (
                    <span className={`nav-count ${criticalCount ? "danger" : ""}`}>{openCount}</span>
                  ) : null}
                  {id === "posture" && score !== undefined ? <span className="nav-count">{score}</span> : null}
                </a>
              ))}
            </div>
          );
        })}

        <div className="nav-foot">
          <div className="segmented small">
            <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
              EN
            </button>
            <button className={lang === "pl" ? "active" : ""} onClick={() => setLang("pl")}>
              PL
            </button>
          </div>
          {health && (
            <div className="muted small">
              {t("Preset: {preset}", { preset: health.policy_preset })} · v{health.policy_version}
            </div>
          )}
        </div>
      </aside>

      <main className="main">
        {error && (
          <Banner tone="danger">
            {t("API unreachable: {error}. Start it with", { error })} <code>python -m sensitive_guard serve</code>
          </Banner>
        )}
        {policyBanner && <Banner tone="ok">{t("Policy reloaded (version {v}).", { v: policyBanner.version })}</Banner>}
        {!data && !error && <p className="muted">{t("Loading workspace…")}</p>}
        {data && <Page />}
      </main>
      <Toasts />
    </div>
  );
}
