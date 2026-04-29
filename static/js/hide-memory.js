/* Memory Tree — Hide/Unhide Memories
 * Exponiert:
 *   window.toggleHidden(memoryId, buttonElement)         (Listenansichten)
 *   window.restoreHidden(memoryId, buttonElement)        (Settings → Einblenden)
 *   window.hideAndReturn(memoryId, buttonElement)        (Detailseite)
 *   window.showToast(message, opts)                      (generisch)
 *
 * Hide-Flow:
 *   1. POST /memories/{id}/toggle-hidden persistiert is_hidden=true
 *   2. Karte wird animiert ausgeblendet
 *   3. Toast „Erinnerung verschoben — Rückgängig" erscheint unten
 *   4. Klick auf „Rückgängig" toggelt erneut → is_hidden=false
 *
 * Detailseite-Flow (hideAndReturn):
 *   1. Hide ausführen
 *   2. Toast-Daten in sessionStorage ablegen (memoryId + Texte)
 *   3. Redirect auf data-hide-redirect (validierter Rücksprung-Pfad)
 *   4. Auf der Zielseite zeigt der Pickup-Loader den Toast inkl. Undo
 *
 * CSRF: Endpunkt verlangt wegen Content-Type: application/json kein Token,
 *       wir senden den X-CSRF-Token-Header trotzdem mit (defense in depth).
 */
(function () {
  "use strict";

  // ── Helpers ──────────────────────────────────────────────────────────────
  function getCsrfCookie() {
    var match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function callToggle(memoryId) {
    var response = await fetch("/memories/" + memoryId + "/toggle-hidden", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": getCsrfCookie(),
      },
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }

  function findCard(button) {
    if (!button) return null;
    return (
      button.closest("[data-memory-id]") ||
      button.closest(".timeline-card-wrapper") ||
      button.closest(".timeline-card") ||
      button.closest(".memory-card") ||
      button.closest(".hanging-memory") ||
      button.closest(".gallery-item") ||
      button.closest(".hidden-memory-card")
    );
  }

  function animateCollapse(card, onDone) {
    if (!card) { if (onDone) onDone(); return; }
    card.style.transition = "opacity 0.3s ease, transform 0.3s ease";
    card.style.opacity = "0";
    card.style.transform = "scale(0.95)";
    setTimeout(function () {
      card.style.maxHeight = card.offsetHeight + "px";
      card.style.overflow = "hidden";
      void card.offsetHeight;
      card.style.transition =
        "max-height 0.3s ease, margin 0.3s ease, padding 0.3s ease";
      card.style.maxHeight = "0";
      card.style.marginTop = "0";
      card.style.marginBottom = "0";
      card.style.paddingTop = "0";
      card.style.paddingBottom = "0";
      setTimeout(function () {
        card.remove();
        if (typeof onDone === "function") onDone();
      }, 300);
    }, 300);
  }

  // ── Toast ────────────────────────────────────────────────────────────────
  // Sicherer Toast: Texte werden ausschließlich via textContent gesetzt,
  // niemals via innerHTML – kein XSS-Risiko durch User-Inhalte.
  function showToast(message, opts) {
    opts = opts || {};
    var existing = document.getElementById("mt-toast");
    if (existing) existing.remove();

    var toast = document.createElement("div");
    toast.id = "mt-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    Object.assign(toast.style, {
      position: "fixed",
      bottom: "24px",
      left: "50%",
      transform: "translateX(-50%) translateY(20px)",
      background: "#1f2937",
      color: "white",
      padding: "10px 12px 10px 18px",
      borderRadius: "14px",
      fontSize: "14px",
      zIndex: "10000",
      boxShadow: "0 12px 32px rgba(0,0,0,0.3)",
      opacity: "0",
      transition: "opacity 0.25s ease, transform 0.25s ease",
      maxWidth: "min(94vw, 520px)",
      display: "flex",
      alignItems: "center",
      gap: "12px",
    });

    var label = document.createElement("span");
    label.textContent = (opts.icon ? opts.icon + " " : "") + message;
    label.style.flex = "1";
    toast.appendChild(label);

    var hideTimer = null;
    function dismiss() {
      if (hideTimer) clearTimeout(hideTimer);
      if (!toast.parentNode) return;
      toast.style.opacity = "0";
      toast.style.transform = "translateX(-50%) translateY(20px)";
      setTimeout(function () {
        if (toast.parentNode) toast.remove();
      }, 250);
    }

    if (opts.actionLabel && typeof opts.onAction === "function") {
      // Trenner zwischen Text und Button
      var divider = document.createElement("span");
      divider.setAttribute("aria-hidden", "true");
      Object.assign(divider.style, {
        width: "1px",
        alignSelf: "stretch",
        background: "rgba(255,255,255,0.18)",
      });
      toast.appendChild(divider);

      var actionBtn = document.createElement("button");
      actionBtn.type = "button";
      // Pfeil-Icon + Label, damit der Button visuell als Aktion erkennbar ist
      actionBtn.textContent = "↶ " + opts.actionLabel;
      Object.assign(actionBtn.style, {
        background: "#fcd34d",        // amber-300, deutlicher Kontrast zum dunklen Toast
        color: "#1f2937",             // dunkler Text auf hellem Button
        border: "none",
        fontWeight: "700",
        fontSize: "14px",
        cursor: "pointer",
        padding: "8px 14px",
        borderRadius: "10px",
        whiteSpace: "nowrap",
        boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
        transition: "background 0.15s ease, transform 0.1s ease",
      });
      actionBtn.addEventListener("mouseenter", function () {
        actionBtn.style.background = "#fbbf24";  // amber-400
      });
      actionBtn.addEventListener("mouseleave", function () {
        actionBtn.style.background = "#fcd34d";
      });
      actionBtn.addEventListener("mousedown", function () {
        actionBtn.style.transform = "scale(0.97)";
      });
      actionBtn.addEventListener("mouseup", function () {
        actionBtn.style.transform = "scale(1)";
      });
      actionBtn.addEventListener("click", function () {
        if (actionBtn.disabled) return;
        actionBtn.disabled = true;
        actionBtn.style.opacity = "0.6";
        opts.onAction();
        dismiss();
      });
      toast.appendChild(actionBtn);
    }

    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Schließen");
    closeBtn.textContent = "✕";
    Object.assign(closeBtn.style, {
      background: "transparent",
      color: "rgba(255,255,255,0.6)",
      border: "none",
      cursor: "pointer",
      fontSize: "14px",
      padding: "4px",
    });
    closeBtn.addEventListener("click", dismiss);
    toast.appendChild(closeBtn);

    document.body.appendChild(toast);
    void toast.offsetHeight;
    toast.style.opacity = "1";
    toast.style.transform = "translateX(-50%) translateY(0)";

    var timeoutMs = opts.duration || 6000;
    hideTimer = setTimeout(dismiss, timeoutMs);
  }
  window.showToast = showToast;

  // ── Undo-Logik ───────────────────────────────────────────────────────────
  // Wiederherstellen bedeutet: erneut /toggle-hidden aufrufen → Server
  // toggelt is_hidden zurück auf false. Bei Erfolg Refresh der Seite, damit
  // die Erinnerung in der Liste wieder erscheint.
  async function performUndo(memoryId) {
    try {
      var data = await callToggle(memoryId);
      if (!data.is_hidden) {
        showToast("Erinnerung wiederhergestellt", { icon: "✓", duration: 2500 });
        setTimeout(function () { window.location.reload(); }, 700);
      } else {
        showToast("Wiederherstellen fehlgeschlagen", { icon: "⚠️", duration: 3000 });
      }
    } catch (err) {
      console.error("[MemoryTree] Undo failed:", err);
      showToast("Wiederherstellen fehlgeschlagen", { icon: "⚠️", duration: 3000 });
    }
  }

  function showHideToast(memoryId) {
    showToast("Erinnerung verschoben", {
      icon: "🙈",
      duration: 6000,
      actionLabel: "Rückgängig",
      onAction: function () { performUndo(memoryId); },
    });
  }

  // ── Public: toggleHidden (Listen) ────────────────────────────────────────
  window.toggleHidden = async function (memoryId, buttonElement) {
    if (!buttonElement || buttonElement.dataset.busy === "true") return;
    buttonElement.dataset.busy = "true";
    try {
      var data = await callToggle(memoryId);
      if (data.is_hidden) {
        var card = findCard(buttonElement);
        animateCollapse(card);
        showHideToast(memoryId);
      } else {
        showToast("Erinnerung wieder sichtbar", { icon: "👁️", duration: 2500 });
      }
    } catch (err) {
      console.error("[MemoryTree] Hide toggle failed:", err);
      showToast("Fehler beim Verstecken", { icon: "⚠️", duration: 3000 });
    } finally {
      buttonElement.dataset.busy = "false";
    }
  };

  // ── Public: hideAndReturn (Detailseite) ──────────────────────────────────
  // Versteckt sofort, legt Pickup-Toast in sessionStorage und springt zum
  // validierten Ursprung zurück. Dort triggert der Pickup-Loader den Toast.
  window.hideAndReturn = async function (memoryId, buttonElement) {
    if (!buttonElement || buttonElement.dataset.busy === "true") return;
    buttonElement.dataset.busy = "true";
    var redirect = buttonElement.getAttribute("data-hide-redirect") || "/";
    // Defense in depth: nur interner Pfad (mit /, nicht //) erlaubt
    if (typeof redirect !== "string" ||
        !redirect.startsWith("/") ||
        redirect.startsWith("//")) {
      redirect = "/";
    }
    try {
      var data = await callToggle(memoryId);
      try {
        sessionStorage.setItem(
          "mt_pending_toast",
          JSON.stringify({ memoryId: memoryId, kind: "hidden", t: Date.now() })
        );
      } catch (_) { /* sessionStorage kann blockiert sein */ }
      window.location.href = redirect;
    } catch (err) {
      console.error("[MemoryTree] hideAndReturn failed:", err);
      showToast("Fehler beim Verstecken", { icon: "⚠️", duration: 3000 });
      buttonElement.dataset.busy = "false";
    }
  };

  // ── Public: restoreHidden (Settings) ─────────────────────────────────────
  window.restoreHidden = async function (memoryId, buttonElement) {
    if (!buttonElement || buttonElement.dataset.busy === "true") return;
    buttonElement.dataset.busy = "true";
    try {
      var data = await callToggle(memoryId);
      if (!data.is_hidden) {
        var card = findCard(buttonElement);
        if (card) {
          card.style.transition = "opacity 0.3s ease, transform 0.3s ease";
          card.style.opacity = "0";
          card.style.transform = "translateX(20px)";
          setTimeout(function () {
            card.remove();
            if (typeof window.updateHiddenCount === "function") {
              window.updateHiddenCount();
            }
          }, 300);
        }
        showToast("Erinnerung wiederhergestellt", { icon: "✓", duration: 2500 });
      }
    } catch (err) {
      console.error("[MemoryTree] Restore failed:", err);
      showToast("Fehler beim Wiederherstellen", { icon: "⚠️", duration: 3000 });
    } finally {
      buttonElement.dataset.busy = "false";
    }
  };

  // ── Pickup: Toast nach Cross-Page-Hide anzeigen ──────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    var raw;
    try { raw = sessionStorage.getItem("mt_pending_toast"); } catch (_) { return; }
    if (!raw) return;
    try { sessionStorage.removeItem("mt_pending_toast"); } catch (_) { /* ignore */ }
    var payload;
    try { payload = JSON.parse(raw); } catch (_) { return; }
    if (!payload || typeof payload.memoryId !== "number") return;
    // 30s Gültigkeit, danach verfällt der Toast
    if (typeof payload.t === "number" && Date.now() - payload.t > 30000) return;
    if (payload.kind === "hidden") {
      showHideToast(payload.memoryId);
    }
  });
})();
