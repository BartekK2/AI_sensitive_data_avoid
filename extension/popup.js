const DEFAULTS = {
  enabled: true,
  apiUrl: "http://127.0.0.1:8080",
  threshold: 0.5,
  locale: "pl",
  blockOnRedact: true,
  failClosed: false,
  employeeId: "",
};

const fields = {
  enabled: document.getElementById("enabled"),
  blockOnRedact: document.getElementById("blockOnRedact"),
  failClosed: document.getElementById("failClosed"),
  apiUrl: document.getElementById("apiUrl"),
  threshold: document.getElementById("threshold"),
  employeeId: document.getElementById("employeeId"),
};
const statusEl = document.getElementById("status");

chrome.storage.sync.get(DEFAULTS, (stored) => {
  fields.enabled.checked = stored.enabled;
  fields.blockOnRedact.checked = stored.blockOnRedact;
  fields.failClosed.checked = stored.failClosed;
  fields.apiUrl.value = stored.apiUrl;
  fields.threshold.value = stored.threshold;
  fields.employeeId.value = stored.employeeId || "";
  ping(stored.apiUrl);
});

for (const [key, el] of Object.entries(fields)) {
  el.addEventListener("change", () => {
    const value = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
    chrome.storage.sync.set({ [key]: value });
    if (key === "apiUrl") ping(el.value);
  });
}

function ping(apiUrl) {
  statusEl.textContent = "sprawdzam…";
  statusEl.dataset.state = "checking";
  chrome.runtime.sendMessage({ type: "HEALTH", apiUrl }, (response) => {
    if (chrome.runtime.lastError || !response || !response.ok) {
      statusEl.textContent = "offline";
      statusEl.dataset.state = "down";
      return;
    }
    statusEl.textContent = "online";
    statusEl.dataset.state = "up";
  });
}
