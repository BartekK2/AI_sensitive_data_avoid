(() => {
  const lib = window.SensitiveGuardLib;
  if (!lib) return;

  const DEFAULTS = {
    enabled: true,
    apiUrl: "http://127.0.0.1:8080",
    threshold: 0.5,
    locale: "pl",
    blockOnRedact: true,
    failClosed: false,
  };

  let settings = { ...DEFAULTS };
  let passThrough = false;
  let pending = false;
  let lastLiveKey = "";
  let liveTimer = 0;

  chrome.storage.sync.get(DEFAULTS, (stored) => {
    settings = { ...DEFAULTS, ...stored };
    renderBadge(null);
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    for (const [key, value] of Object.entries(changes)) settings[key] = value.newValue;
  });

  function askBackground(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(response || { ok: false, error: "brak odpowiedzi tła" });
      });
    });
  }

  async function scanText(text, options = {}) {
    return askBackground({
      type: "SCAN",
      apiUrl: settings.apiUrl,
      text,
      threshold: settings.threshold,
      locale: settings.locale,
      record: Boolean(options.record),
      destination: location.hostname,
    });
  }

  function ensureUi() {
    let host = document.getElementById("sg-root");
    if (host) return host;
    host = document.createElement("div");
    host.id = "sg-root";
    host.setAttribute("data-sg-ui", "1");
    host.innerHTML = `
      <div class="sg-badge" id="sg-badge" hidden>sensitive-guard</div>
      <div class="sg-modal" id="sg-modal" hidden>
        <div class="sg-card">
          <div class="sg-kicker">sensitive-guard · Laya</div>
          <h2 id="sg-title">Wysyłka wstrzymana</h2>
          <p id="sg-lead"></p>
          <ul id="sg-entities"></ul>
          <pre id="sg-redacted"></pre>
          <div class="sg-actions">
            <button type="button" id="sg-cancel">Zostaw</button>
            <button type="button" id="sg-redact">Wyślij zredagowane</button>
            <button type="button" class="sg-danger" id="sg-anyway">Wyślij mimo to</button>
          </div>
        </div>
      </div>
    `;
    document.documentElement.appendChild(host);
    host.querySelector("#sg-cancel").addEventListener("click", hideModal);
    host.querySelector("#sg-redact").addEventListener("click", () => finishHeld("redact"));
    host.querySelector("#sg-anyway").addEventListener("click", () => finishHeld("anyway"));
    return host;
  }

  function renderBadge(scan) {
    const host = ensureUi();
    const badge = host.querySelector("#sg-badge");
    if (!settings.enabled) {
      badge.hidden = true;
      return;
    }
    badge.hidden = false;
    badge.className = "sg-badge";
    if (!scan) {
      badge.textContent = "guard · gotowy";
      return;
    }
    if (scan.action === "pending") {
      badge.textContent = "skanuję…";
      return;
    }
    if (scan.error) {
      badge.classList.add("sg-warn");
      badge.textContent = "guard · brak API";
      return;
    }
    if (scan.action === "block") {
      badge.classList.add("sg-block");
      badge.textContent = `blokada · ${scan.risk || "critical"}`;
      return;
    }
    if (scan.action === "redact") {
      badge.classList.add("sg-redact");
      badge.textContent = `PII · ${scan.entities?.length || 0}`;
      return;
    }
    badge.classList.add("sg-ok");
    badge.textContent = "czysty";
  }

  let held = null;

  function hideModal() {
    const modal = ensureUi().querySelector("#sg-modal");
    modal.hidden = true;
    held = null;
  }

  function showHold(scan, composer, sendButton) {
    held = { scan, composer, sendButton };
    const host = ensureUi();
    const modal = host.querySelector("#sg-modal");
    const critical = scan.action === "block";
    host.querySelector("#sg-title").textContent = critical
      ? "Wysyłka zablokowana"
      : "Wiadomość zawiera dane wrażliwe";
    host.querySelector("#sg-lead").textContent = critical
      ? scan.blocked_reason || "Laya wykryła dane, których nie wolno wysłać do modelu."
      : "Możesz wysłać wersję z maskami albo przerwać.";
    const list = host.querySelector("#sg-entities");
    list.innerHTML = "";
    for (const entity of scan.entities || []) {
      const item = document.createElement("li");
      item.textContent = `${entity.label} · ${entity.category} · ${entity.risk}`;
      list.appendChild(item);
    }
    host.querySelector("#sg-redacted").textContent = scan.redacted || "";
    host.querySelector("#sg-anyway").hidden = critical;
    host.querySelector("#sg-redact").hidden = !scan.redacted;
    modal.hidden = false;
  }

  function finishHeld(mode) {
    if (!held) return;
    const { composer, sendButton, scan } = held;
    hideModal();
    if (mode === "redact" && scan.redacted) {
      lib.setComposerText(composer, scan.redacted);
    }
    replaySend(composer, sendButton);
  }

  function replaySend(composer, sendButton) {
    passThrough = true;
    try {
      const button = sendButton || lib.findSendButton(composer);
      if (button) button.click();
      else if (composer) {
        composer.dispatchEvent(
          new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true, cancelable: true })
        );
      }
    } finally {
      setTimeout(() => {
        passThrough = false;
      }, 250);
    }
  }

  async function gateEvent(event, sendButton) {
    if (!settings.enabled || passThrough || pending) return;
    const composer = lib.findComposer();
    const text = lib.getComposerText(composer);
    if (!text) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    pending = true;
    renderBadge({ action: "pending" });

    const response = await scanText(text, { record: true });
    pending = false;

    if (!response.ok) {
      renderBadge({ error: true });
      if (settings.failClosed) {
        showHold(
          { action: "block", blocked_reason: response.error || "API niedostępne", entities: [], redacted: text },
          composer,
          sendButton
        );
        return;
      }
      replaySend(composer, sendButton);
      return;
    }

    const scan = response.scan;
    renderBadge(scan);
    const decision = lib.shouldHold(scan, settings);
    if (!decision.hold) {
      replaySend(composer, sendButton);
      return;
    }
    showHold(scan, composer, sendButton);
  }

  function onKeyDown(event) {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    if (!lib.isEditable(event.target)) return;
    gateEvent(event, lib.findSendButton(lib.editableRoot(event.target)));
  }

  function onClick(event) {
    if (!lib.looksLikeSend(event.target)) return;
    const button = event.target.closest("button, [role='button'], [type='submit']");
    gateEvent(event, button);
  }

  function scheduleLiveScan() {
    clearTimeout(liveTimer);
    liveTimer = window.setTimeout(runLiveScan, 450);
  }

  async function runLiveScan() {
    if (!settings.enabled) return;
    const text = lib.getComposerText();
    if (!text) {
      lastLiveKey = "";
      renderBadge(null);
      return;
    }
    if (text === lastLiveKey) return;
    lastLiveKey = text;
    const response = await scanText(text);
    if (text !== lastLiveKey) return;
    if (!response.ok) {
      renderBadge({ error: true });
      return;
    }
    renderBadge(response.scan);
  }

  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("input", scheduleLiveScan, true);
  ensureUi();
})();
