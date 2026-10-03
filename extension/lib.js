/* Shared composer helpers — no chrome.* APIs, usable from the mock page too. */
(function (root) {
  const SEND_RE =
    /\b(send|submit|wyślij|wyslij|envoyer|senden|invia|enviar|absenden|paper[- ]?plane|arrow up)\b/i;
  const IGNORE_RE =
    /\b(new chat|nowy czat|settings|ustawienia|share|udostępnij|attach|załącz|stop|zatrzymaj|voice|mikrofon|regenerate|copy|kopiuj)\b/i;

  function isVisible(el) {
    if (!el || !(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
      return false;
    }
    const box = el.getBoundingClientRect();
    return box.width > 8 && box.height > 8;
  }

  function isEditable(el) {
    if (!el || !(el instanceof Element)) return false;
    if (el.closest("[data-sg-ui]")) return false;
    const tag = el.tagName;
    if (tag === "TEXTAREA") return true;
    if (tag === "INPUT") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      return type === "text" || type === "search" || type === "";
    }
    if (el.getAttribute("contenteditable") === "true") return true;
    if (el.getAttribute("role") === "textbox") return true;
    return Boolean(el.closest('[contenteditable="true"], [role="textbox"]'));
  }

  function editableRoot(el) {
    if (!el || !(el instanceof Element)) return null;
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") return el;
    return el.closest('[contenteditable="true"], [role="textbox"], textarea, input');
  }

  function readText(el) {
    if (!el) return "";
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") return el.value || "";
    return (el.innerText || el.textContent || "").replace(/\u00a0/g, " ");
  }

  function findComposer() {
    const active = editableRoot(document.activeElement);
    if (active && isVisible(active) && readText(active).trim()) return active;
    if (active && isVisible(active)) return active;

    const nodes = [
      ...document.querySelectorAll(
        'textarea, input[type="text"], input[type="search"], [contenteditable="true"], [role="textbox"]'
      ),
    ].filter((el) => isVisible(el) && !el.closest("[data-sg-ui]"));

    if (!nodes.length) return null;

    const viewportH = window.innerHeight || 800;
    nodes.sort((a, b) => {
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      const bottomBias = (ra.top > viewportH * 0.35 ? 80 : 0) - (rb.top > viewportH * 0.35 ? 80 : 0);
      const area = rb.width * rb.height - ra.width * ra.height;
      return bottomBias || area;
    });
    return nodes[0];
  }

  function getComposerText(el) {
    return readText(el || findComposer()).trim();
  }

  function setComposerText(el, text) {
    if (!el) return false;
    el.focus();
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")
        || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
      if (proto && proto.set) proto.set.call(el, text);
      else el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    try {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      selection.removeAllRanges();
      selection.addRange(range);
      const ok = document.execCommand("insertText", false, text);
      if (ok) return true;
    } catch (_err) {
      /* fall through */
    }
    el.textContent = text;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    return true;
  }

  function labelOf(el) {
    if (!el || !(el instanceof Element)) return "";
    return [
      el.getAttribute("aria-label"),
      el.getAttribute("title"),
      el.getAttribute("data-testid"),
      el.getAttribute("data-qa"),
      el.getAttribute("name"),
      el.textContent,
    ]
      .filter(Boolean)
      .join(" ");
  }

  function looksLikeSend(el) {
    if (!el || !(el instanceof Element)) return false;
    if (el.closest("[data-sg-ui]")) return false;
    const target = el.closest("button, [role='button'], [type='submit']");
    if (!target || !isVisible(target)) return false;
    if (target.disabled || target.getAttribute("aria-disabled") === "true") return false;
    const label = labelOf(target);
    if (IGNORE_RE.test(label)) return false;
    if (SEND_RE.test(label)) return true;
    if (target.getAttribute("type") === "submit") return true;
    if (target.querySelector('svg[class*="send" i], [data-icon="send"]')) return true;
    return false;
  }

  function findSendButton(composer) {
    const scope =
      (composer && (composer.closest("form") || composer.closest("footer") || composer.parentElement)) ||
      document;
    const buttons = [...scope.querySelectorAll("button, [role='button'], [type='submit']")].filter(isVisible);
    let best = null;
    let bestScore = 0;
    for (const button of buttons) {
      const label = labelOf(button);
      if (IGNORE_RE.test(label)) continue;
      let score = 0;
      if (SEND_RE.test(label)) score += 8;
      if ((button.getAttribute("data-testid") || "").toLowerCase().includes("send")) score += 10;
      if (button.getAttribute("type") === "submit") score += 4;
      if (composer) {
        const a = button.getBoundingClientRect();
        const b = composer.getBoundingClientRect();
        const near = Math.abs(a.top - b.top) < 140 && Math.abs(a.left - b.right) < 280;
        if (near) score += 3;
      }
      if (score > bestScore) {
        best = button;
        bestScore = score;
      }
    }
    return bestScore >= 3 ? best : null;
  }

  function shouldHold(scan, settings) {
    const action = scan && scan.action;
    if (action === "block") return { hold: true, kind: "block" };
    if (action === "redact" && settings.blockOnRedact !== false) return { hold: true, kind: "redact" };
    return { hold: false, kind: action || "allow" };
  }

  root.SensitiveGuardLib = {
    isEditable,
    isVisible,
    findComposer,
    getComposerText,
    setComposerText,
    looksLikeSend,
    findSendButton,
    shouldHold,
    editableRoot,
  };
})(typeof window !== "undefined" ? window : globalThis);
