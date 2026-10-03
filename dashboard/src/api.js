async function req(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let text = await response.text();
    try {
      const parsed = JSON.parse(text);
      text = parsed.detail ? (typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail)) : text;
    } catch {
      /* plain text */
    }
    throw new Error(text || `HTTP ${response.status}`);
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("json")) return response.json();
  return response.text();
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });

function qs(params = {}) {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!entries.length) return "";
  return "?" + new URLSearchParams(entries.map(([key, value]) => [key, String(value)])).toString();
}

export const api = {
  health: () => req("/health"),
  workspace: () => req("/v1/admin/workspace"),
  metrics: () => req("/v1/admin/metrics"),

  saveEmployee: (body) => req("/v1/admin/employees", json("POST", body)),
  deleteEmployee: (id) => req(`/v1/admin/employees/${id}`, { method: "DELETE" }),
  saveRole: (body) => req("/v1/admin/roles", json("POST", body)),
  deleteRole: (id) => req(`/v1/admin/roles/${id}`, { method: "DELETE" }),
  saveCategory: (body) => req("/v1/admin/categories", json("POST", body)),
  deleteCategory: (id) => req(`/v1/admin/categories/${id}`, { method: "DELETE" }),
  saveWhitelist: (body) => req("/v1/admin/whitelist", json("POST", body)),
  deleteWhitelist: (id) => req(`/v1/admin/whitelist/${id}`, { method: "DELETE" }),

  incidents: (params) => req(`/v1/admin/incidents${qs({ paged: true, ...params })}`),
  patchIncident: (id, body) => req(`/v1/admin/incidents/${id}`, json("PATCH", body)),
  bulkIncidents: (body) => req("/v1/admin/incidents/bulk", json("POST", body)),
  deleteIncident: (id) => req(`/v1/admin/incidents/${id}`, { method: "DELETE" }),
  incidentsExportUrl: (params) => `/v1/admin/incidents/export${qs(params)}`,

  policy: () => req("/v1/admin/policy"),
  patchPolicy: (body) => req("/v1/admin/policy", json("PATCH", body)),
  putPolicy: (body) => req("/v1/admin/policy", json("PUT", body)),
  usePreset: (name) => req(`/v1/admin/policy/preset/${name}`, { method: "POST" }),
  policyHistory: () => req("/v1/admin/policy/history"),
  policyExportUrl: () => "/v1/admin/policy/export",
  controls: () => req("/v1/admin/controls"),
  patchControl: (id, body) => req(`/v1/admin/controls/${id}`, json("PATCH", body)),

  budget: () => req("/v1/admin/budget"),
  resetBudget: () => req("/v1/admin/budget/reset", { method: "POST" }),

  signatures: () => req("/v1/admin/signatures"),
  saveSignature: (body) => req("/v1/admin/signatures", json("POST", body)),
  patchSignature: (id, body) => req(`/v1/admin/signatures/${id}`, json("PATCH", body)),
  deleteSignature: (id) => req(`/v1/admin/signatures/${id}`, { method: "DELETE" }),
  importSignatures: (body) => req("/v1/admin/signatures/import", json("POST", body)),

  audit: (params) => req(`/v1/admin/audit${qs(params)}`),
  auditExportUrl: (params) => `/v1/admin/audit${qs(params)}`,

  demoReset: (keepLive = true) => req(`/v1/admin/demo/reset?keep_live=${keepLive}`, { method: "POST" }),
  demoClearLive: () => req("/v1/admin/demo/clear-live", { method: "POST" }),

  scan: (body) => req("/v1/scan", json("POST", body)),

  tryAgent: async (employeeId, text, options = {}) => {
    const response = await fetch("/net/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Employee-Id": employeeId,
        Authorization: "Bearer sk-helios-demo",
      },
      body: JSON.stringify({
        model: options.model || "gpt-4o-mini",
        messages: [{ role: "user", content: text }],
        ...(options.tools ? { tools: options.tools } : {}),
      }),
    });
    let data = {};
    try {
      data = await response.json();
    } catch {
      data = { error: `HTTP ${response.status}` };
    }
    return {
      status: response.status,
      data,
      policyVersion: response.headers.get("X-Helios-Policy-Version"),
      requestId: response.headers.get("X-Helios-Request-Id"),
      action: response.headers.get("X-Helios-Action"),
    };
  },
};
