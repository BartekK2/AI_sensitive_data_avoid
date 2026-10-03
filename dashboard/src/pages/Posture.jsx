import { Badge, Empty, Labels, RelativeTime } from "../components/ui.jsx";
import RichText from "../components/RichText.jsx";
import Strata from "../components/Strata.jsx";
import Wordmark from "../components/Wordmark.jsx";
import { navigate } from "../router.js";
import { useApp } from "../store.jsx";

export default function Posture() {
  const { t, data, metrics } = useApp();
  if (!metrics) return <p className="muted">{t("Loading")}…</p>;

  const open = (data.incidents || [])
    .filter((item) => item.status === "open")
    .sort((a, b) => (b.last_seen_at || b.created_at || "").localeCompare(a.last_seen_at || a.created_at || ""));

  return (
    <div>
      <section className="hero">
        <div className="hero-copy">
          <Wordmark className="kicker" />
          <h1>{t("Nothing sensitive leaves the machine.")}</h1>
          <p className="lead">{t("A national ID or an injection attempt is stopped here, before the model sees it.")}</p>
          <div className="stats">
            <button type="button" onClick={() => navigate("incidents", { action: "block" })}>
              <b>{metrics.today.block}</b>
              <span>{t("Blocked")}</span>
            </button>
            <button type="button" onClick={() => navigate("incidents", { status: "open" })}>
              <b>{metrics.incidents.open}</b>
              <span>{t("Open incidents")}</span>
            </button>
            <button type="button" onClick={() => navigate("incidents")}>
              <b>{metrics.today.allow}</b>
              <span>{t("Allowed")}</span>
            </button>
          </div>
        </div>
        <Strata />
      </section>

      <section className="section">
        <div className="section-head">
          <h2>{t("Open incidents")}</h2>
          <a className="link" href="#incidents">
            {t("Incidents")}
          </a>
        </div>
        {!open.length && <Empty>{t("All quiet. No open incidents.")}</Empty>}
        {open.slice(0, 8).map((item) => (
          <article key={item.id} className={`incident ${item.action} compact clickable`} onClick={() => navigate("incidents", { id: item.id })}>
            <div className="row">
              <strong>{item.employee_name}</strong>
              <Badge tone={item.risk}>{t(item.risk)}</Badge>
              <Badge tone={item.action}>{t(item.action)}</Badge>
              <span className="muted">{item.destination}</span>
              <span className="muted right">
                <RelativeTime value={item.last_seen_at || item.created_at} />
              </span>
            </div>
            <p className="muted small">
              {item.team} · {item.role_name} · <Labels items={item.labels} />
            </p>
            <RichText className="excerpt" text={item.redacted || item.prompt_excerpt} />
          </article>
        ))}
      </section>
    </div>
  );
}
