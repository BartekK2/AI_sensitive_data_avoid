export function parseHash(hash = window.location.hash) {
  const raw = (hash || "").replace(/^#\/?/, "");
  const [page, query = ""] = raw.split("?");
  const params = Object.fromEntries(new URLSearchParams(query).entries());
  return { page: page || "posture", params };
}

export function hrefFor(page, params = {}) {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== "");
  const query = entries.length ? "?" + new URLSearchParams(entries).toString() : "";
  return `#${page}${query}`;
}

export function navigate(page, params = {}) {
  window.location.hash = hrefFor(page, params);
}
