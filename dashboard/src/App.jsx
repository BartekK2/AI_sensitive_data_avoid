import Posture from "./pages/Posture.jsx";
import Incidents from "./pages/Incidents.jsx";
import People from "./pages/People.jsx";
import Roles from "./pages/Roles.jsx";
import Categories from "./pages/Categories.jsx";
import Whitelist from "./pages/Whitelist.jsx";
import Policy from "./pages/Policy.jsx";
import Wordmark from "./components/Wordmark.jsx";
import { useApp } from "./store.jsx";

const PAGES = {
  posture: Posture,
  incidents: Incidents,
  people: People,
  roles: Roles,
  categories: Categories,
  whitelist: Whitelist,
  policy: Policy,
};

const NAV = [
  ["posture", "Overview"],
  ["incidents", "Incidents"],
  ["people", "People"],
  ["roles", "Roles"],
  ["categories", "Categories"],
  ["whitelist", "Whitelist"],
  ["policy", "Policy"],
];

export default function App() {
  const { t, lang, setLang, route, error } = useApp();
  const Page = PAGES[route.page] || Posture;

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">
          <Wordmark />
        </div>
        <nav>
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} className={route.page === id ? "active" : ""}>
              {t(label)}
            </a>
          ))}
        </nav>
        <div className="nav-foot">
          <div className="segmented small" role="group" aria-label={t("Language")}>
            <button className={lang === "pl" ? "active" : ""} onClick={() => setLang("pl")}>
              PL
            </button>
            <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
              EN
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        {error && <p className="danger">{error}</p>}
        <Page />
      </main>
    </div>
  );
}
