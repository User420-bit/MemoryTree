// Memory Tree — Zeitstrahl: Drag & Drop Sortierung innerhalb Datumsgruppen
// Vanilla JS, keine externen Abhängigkeiten

(function () {
  "use strict";

  if (window._timelineSortInit) return;
  window._timelineSortInit = true;

  function initSortable() {
    var dateGroups = document.querySelectorAll(".date-group");

    dateGroups.forEach(function (group) {
      var cards = group.querySelectorAll(".timeline-card-wrapper");

      // Drag-Handles nur anzeigen wenn mehr als 1 Karte in der Gruppe
      if (cards.length <= 1) return;

      cards.forEach(function (card) {
        var handle = card.querySelector(".drag-handle");
        if (handle) {
          handle.classList.remove("hidden");
          handle.classList.add("flex");
        }
      });

      var draggedEl = null;
      var placeholder = null;

      cards.forEach(function (card) {
        var handle = card.querySelector(".drag-handle");
        if (!handle) return;

        handle.addEventListener("pointerdown", function (e) {
          e.preventDefault();
          draggedEl = card;

          // Visuelles Feedback
          card.style.opacity = "0.5";
          card.style.transition = "none";

          // Placeholder erstellen
          placeholder = document.createElement("div");
          placeholder.className =
            "h-2 bg-emerald-300 rounded-full mx-4 my-1 transition-all";

          document.addEventListener("pointermove", onDragMove);
          document.addEventListener("pointerup", onDragEnd);
        });
      });

      function onDragMove(e) {
        if (!draggedEl) return;

        var siblings = Array.from(
          group.querySelectorAll(".timeline-card-wrapper")
        );
        var target = null;

        for (var i = 0; i < siblings.length; i++) {
          var sibling = siblings[i];
          if (sibling === draggedEl) continue;
          var rect = sibling.getBoundingClientRect();
          var midY = rect.top + rect.height / 2;
          if (e.clientY < midY) {
            target = sibling;
            break;
          }
        }

        // Placeholder positionieren
        if (placeholder.parentNode) placeholder.remove();
        if (target) {
          group.insertBefore(placeholder, target);
        } else {
          group.appendChild(placeholder);
        }
      }

      function onDragEnd() {
        if (!draggedEl) return;

        document.removeEventListener("pointermove", onDragMove);
        document.removeEventListener("pointerup", onDragEnd);

        // Element an Placeholder-Position einfügen
        if (placeholder && placeholder.parentNode) {
          group.insertBefore(draggedEl, placeholder);
          placeholder.remove();
        }

        // Styling zurücksetzen
        draggedEl.style.opacity = "";
        draggedEl.style.transition = "";
        draggedEl = null;
        placeholder = null;

        // Neue Reihenfolge an Server senden
        saveOrder(group);
      }
    });
  }

  function saveOrder(group) {
    var cards = group.querySelectorAll(".timeline-card-wrapper");
    var order = [];

    cards.forEach(function (card, index) {
      var id = card.getAttribute("data-memory-id");
      if (id) {
        order.push({ id: parseInt(id, 10), sort_order: index });
      }
    });

    if (order.length === 0) return;

    // CSRF-Token aus Cookie lesen
    var csrfToken = "";
    var cookies = document.cookie.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf("csrf_token=") === 0) {
        csrfToken = c.substring("csrf_token=".length);
        break;
      }
    }

    fetch("/memories/reorder", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({ order: order }),
    }).catch(function (err) {
      console.error("[MemoryTree] Reorder save failed:", err);
    });
  }

  // Init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSortable);
  } else {
    initSortable();
  }
})();
