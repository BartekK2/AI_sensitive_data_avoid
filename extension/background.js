const DEFAULT_API = "http://127.0.0.1:8080";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "SCAN") {
    scan(message).then(sendResponse);
    return true;
  }
  if (message.type === "HEALTH") {
    health(message.apiUrl).then(sendResponse);
    return true;
  }
  return false;
});

async function health(apiUrl) {
  const base = (apiUrl || DEFAULT_API).replace(/\/$/, "");
  try {
    const response = await fetch(`${base}/health`);
    if (!response.ok) return { ok: false, error: `HTTP ${response.status}` };
    return { ok: true, ...(await response.json()) };
  } catch (error) {
    return { ok: false, error: String(error.message || error) };
  }
}

async function scan(message) {
  const base = (message.apiUrl || DEFAULT_API).replace(/\/$/, "");
  try {
    const response = await fetch(`${base}/v1/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: message.text,
          threshold: message.threshold ?? 0.5,
          locale: message.locale || "pl",
          region: "PL",
          record: Boolean(message.record),
          employee_id: message.employeeId || null,
          destination: message.destination || "ai_chat",
        }),
    });
    if (!response.ok) {
      return { ok: false, error: `HTTP ${response.status}` };
    }
    return { ok: true, scan: await response.json() };
  } catch (error) {
    return { ok: false, error: String(error.message || error) };
  }
}
