// Memory Tree — Zeitstrahl: Kategorie-Filter und Pin-Toggle
// Vanilla JS, keine externen Abhängigkeiten

(function () {
  "use strict";

  var activeCategory = "all";

  // ── Kategorie-Filter anwenden ─────────────────────────────────────────
  function applyFilters() {
    var content = document.getElementById("timeline-content");
    if (!content) return;

    var cards = content.querySelectorAll(".timeline-card-wrapper");
    var yearDividers = content.querySelectorAll(".year-divider");
    var noResults = document.getElementById("no-filter-results");
    var anyVisible = false;

    // Karten filtern
    cards.forEach(function (card) {
      var cat = card.getAttribute("data-category");
      var show = (activeCategory === "all" || cat === activeCategory);
      card.style.display = show ? "" : "none";
      if (show) anyVisible = true;
    });

    // Jahres-Trenner: nur anzeigen wenn mindestens eine Karte in diesem Jahr sichtbar
    yearDividers.forEach(function (divider) {
      var year = divider.getAttribute("data-year");
      var hasVisible = false;
      cards.forEach(function (card) {
        if (card.getAttribute("data-year") === year && card.style.display !== "none") {
          hasVisible = true;
        }
      });
      divider.style.display = hasVisible ? "" : "none";
    });

    // Kein-Treffer Hinweis
    if (noResults) {
      if (anyVisible) {
        noResults.classList.add("hidden");
        noResults.classList.remove("flex");
      } else {
        noResults.classList.remove("hidden");
        noResults.classList.add("flex");
      }
    }
  }

  // ── Filter-Buttons einrichten ──────────────────────────────────────────
  function setupCategoryFilters() {
    var buttons = document.querySelectorAll(".timeline-filter-btn[data-filter-category]");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        activeCategory = btn.getAttribute("data-filter-category");
        applyFilters();
      });
    });
  }

  // ── Init ──────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    setupCategoryFilters();
  });

})();
