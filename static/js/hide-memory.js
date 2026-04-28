/* Memory Tree — Hide/Unhide Memories
 * Exponiert:
 *   window.toggleHidden(memoryId, buttonElement)
 *   window.restoreHidden(memoryId, buttonElement)
 *
 * CSRF: Der Endpunkt /memories/{id}/toggle-hidden verlangt wegen
 *       Content-Type application/json KEIN CSRF-Token (siehe CSRF-Middleware-
 *       Ausnahme). Wir senden aber trotzdem den X-CSRF-Token-Header mit,
 *       falls die Policy später verschärft wird.
 */
(function () {
  "use strict";

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
    card.style.transition = "opacity 0.35s ease, transform 0.35s ease";
    card.style.opacity = "0";
    card.style.transform = "scale(0.95)";
    setTimeout(function () {
      card.style.maxHeight = card.offsetHeight + "px";
      card.style.overflow = "hidden";
      // Reflow
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
      }, 320);
    }, 360);
  }

  function showToast(message, icon) {
    var existing = document.getElementById("mt-toast");
    if (existing) existing.remove();

    var toast = document.createElement("div");
    toast.id = "mt-toast";
    toast.setAttribute("role", "status");
    Object.assign(toast.style, {
      position: "fixed",
      bottom: "24px",
      left: "50%",
      transform: "translateX(-50%) translateY(20px)",
      background: "#1f2937",
      color: "white",
      padding: "12px 20px",
      borderRadius: "12px",
      fontSize: "13px",
      zIndex: "10000",
      boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
      opacity: "0",
      transition: "opacity 0.3s ease, transform 0.3s ease",
      maxWidth: "90vw",
    });
    toast.textContent = (icon || "") + " " + message;
    document.body.appendChild(toast);
    void toast.offsetHeight;
    toast.style.opacity = "1";
    toast.style.transform = "translateX(-50%) translateY(0)";
    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(-50%) translateY(20px)";
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 3200);
  }

  window.toggleHidden = async function (memoryId, buttonElement) {
    if (!buttonElement || buttonElement.dataset.busy === "true") return;
    buttonElement.dataset.busy = "true";
    try {
      var data = await callToggle(memoryId);
      if (data.is_hidden) {
        var card = findCard(buttonElement);
        if (card) {
          animateCollapse(card);
        }
        showToast(
          "Erinnerung versteckt — Wiederherstellen in den Einstellungen",
          "🙈"
        );
      } else {
        // Ausnahmefall: von ausgeblendet → sichtbar direkt am Button
        showToast("Erinnerung wieder sichtbar", "👁️");
      }
    } catch (err) {
      console.error("[MemoryTree] Hide toggle failed:", err);
      showToast("Fehler beim Verstecken", "⚠️");
    } finally {
      buttonElement.dataset.busy = "false";
    }
  };

  window.restoreHidden = async function (memoryId, buttonElement) {
    if (!buttonElement || buttonElement.dataset.busy === "true") return;
    buttonElement.dataset.busy = "true";
    try {
      var data = await callToggle(memoryId);
      if (!data.is_hidden) {
        var card = findCard(buttonElement);
        if (card) {
          card.style.transition =
            "opacity 0.3s ease, transform 0.3s ease";
          card.style.opacity = "0";
          card.style.transform = "translateX(20px)";
          setTimeout(function () {
            card.remove();
            if (typeof window.updateHiddenCount === "function") {
              window.updateHiddenCount();
            }
          }, 300);
        }
        showToast("Erinnerung wiederhergestellt", "✓");
      }
    } catch (err) {
      console.error("[MemoryTree] Restore failed:", err);
      showToast("Fehler beim Wiederherstellen", "⚠️");
    } finally {
      buttonElement.dataset.busy = "false";
    }
  };
})();
