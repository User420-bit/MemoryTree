// Memory Tree — Minimal tree page JS
// Only used if tree.html loads this file (currently inlined in template)

(function () {
  "use strict";

  // Apply data-attribute driven styles (positions, colors)
  function applyDataStyles() {
    document.querySelectorAll("[data-pos-top][data-pos-left]").forEach(function (el) {
      el.style.top = el.dataset.posTop;
      el.style.left = el.dataset.posLeft;
      el.style.transform = "translateX(-50%)";
    });
    document.querySelectorAll("[data-bg-color]").forEach(function (el) {
      el.style.backgroundColor = el.dataset.bgColor + "20";
    });
  }

  document.addEventListener("DOMContentLoaded", applyDataStyles);
})();
