async function req(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export const api = {
  workspace: () => req("/v1/admin/workspace"),
  saveEmployee: (body) => req("/v1/admin/employees", { method: "POST", body: JSON.stringify(body) }),
  deleteEmployee: (id) => req(`/v1/admin/employees/${id}`, { method: "DELETE" }),
  saveRole: (body) => req("/v1/admin/roles", { method: "POST", body: JSON.stringify(body) }),
  deleteRole: (id) => req(`/v1/admin/roles/${id}`, { method: "DELETE" }),
  saveCategory: (body) => req("/v1/admin/categories", { method: "POST", body: JSON.stringify(body) }),
  deleteCategory: (id) => req(`/v1/admin/categories/${id}`, { method: "DELETE" }),
  saveWhitelist: (body) => req("/v1/admin/whitelist", { method: "POST", body: JSON.stringify(body) }),
  deleteWhitelist: (id) => req(`/v1/admin/whitelist/${id}`, { method: "DELETE" }),
  patchIncident: (id, body) => req(`/v1/admin/incidents/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  tryAgent: async (employeeId, text) => {
    const response = await fetch("/net/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Employee-Id": employeeId,
        Authorization: "Bearer sk-helios-demo",
      },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        messages: [{ role: "user", content: text }],
      }),
    });
    let data = {};
    try {
      data = await response.json();
    } catch {
      data = { error: `HTTP ${response.status}` };
    }
    return { status: response.status, data };
  },
};
