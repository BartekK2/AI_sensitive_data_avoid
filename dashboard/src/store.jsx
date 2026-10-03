import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { translate } from "./i18n.js";
import { navigate, parseHash } from "./router.js";

const AppContext = createContext(null);

const LANG_KEY = "helios.lang";
const AUDIENCE_KEY = "helios.audience";
const POLL_MS = 4000;

export function AppProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem(LANG_KEY) || "en");
  const [audience, setAudienceState] = useState(() => localStorage.getItem(AUDIENCE_KEY) || "manager");
  const [route, setRoute] = useState(() => parseHash());
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState([]);
  const [policyBanner, setPolicyBanner] = useState(null);
  const seenOpen = useRef(null);
  const seenPolicy = useRef(null);
  const toastId = useRef(0);

  const setLang = useCallback((value) => {
    localStorage.setItem(LANG_KEY, value);
    setLangState(value);
  }, []);
  const setAudience = useCallback((value) => {
    localStorage.setItem(AUDIENCE_KEY, value);
    setAudienceState(value);
  }, []);

  const t = useCallback((key, vars) => translate(lang, key, vars), [lang]);

  const toast = useCallback((message, options = {}) => {
    const id = ++toastId.current;
    setToasts((items) => [...items, { id, message, ...options }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), options.ttl || 7000);
    return id;
  }, []);
  const dismissToast = useCallback((id) => setToasts((items) => items.filter((item) => item.id !== id)), []);

  const refresh = useCallback(async () => {
    try {
      const [workspace, met, hp] = await Promise.all([api.workspace(), api.metrics(), api.health()]);
      setData(workspace);
      setMetrics(met);
      setHealth(hp);
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // New-incident toast with a deep link.
  useEffect(() => {
    if (!data) return;
    const open = data.stats?.open_incidents ?? 0;
    if (seenOpen.current === null) {
      seenOpen.current = open;
      return;
    }
    if (open > seenOpen.current) {
      const fresh = (data.incidents || [])
        .filter((item) => item.status === "open")
        .sort((a, b) => (b.last_seen_at || b.created_at || "").localeCompare(a.last_seen_at || a.created_at || ""));
      const newest = fresh[0];
      const delta = open - seenOpen.current;
      const message = newest
        ? t("New incident: {name} on {dest} · {labels}", {
            name: newest.employee_name,
            dest: newest.destination,
            labels: (newest.labels || []).join(", "),
          })
        : t("{n} new incidents", { n: delta });
      toast(message, {
        tone: newest?.risk === "critical" ? "danger" : "warn",
        count: delta,
        onClick: newest ? () => navigate("incidents", { id: newest.id }) : undefined,
      });
    }
    seenOpen.current = open;
  }, [data, t, toast]);

  // Policy reloaded banner.
  useEffect(() => {
    if (!health) return;
    const version = health.policy_version;
    if (seenPolicy.current === null) {
      seenPolicy.current = version;
      return;
    }
    if (version !== seenPolicy.current) {
      setPolicyBanner({ version, at: Date.now() });
      window.setTimeout(() => setPolicyBanner(null), 8000);
    }
    seenPolicy.current = version;
  }, [health]);

  const value = useMemo(
    () => ({
      lang, setLang, audience, setAudience, t,
      route, navigate,
      data, metrics, health, error, refresh,
      toasts, toast, dismissToast,
      policyBanner,
    }),
    [lang, setLang, audience, setAudience, t, route, data, metrics, health, error, refresh, toasts, toast, dismissToast, policyBanner]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}
