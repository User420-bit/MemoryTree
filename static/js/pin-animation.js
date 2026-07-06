/**
 * Pin-Animation für Memory Tree
 * Robust fly-animations for pin/unpin with full error handling.
 * Single source of truth for togglePin — no other file should define it.
 */
(function () {
  "use strict";

  // Übersetzte Strings: von tree.html/timeline.html per window.PIN_STR
  // injiziert (diese Datei ist statisch, kann kein Jinja rendern).
  var STR = window.PIN_STR || {
    pinToTree: "An den Baum pinnen",
    unpinFromTree: "Vom Baum lösen",
    maxPinnedAlert: "Maximal 8 Erinnerungen können an den Baum gepinnt werden.",
    emptyTreeHint: "Pinne Erinnerungen im Zeitstrahl um sie hier zu sehen 🌿"
  };

  // === STATE: prevent double-clicks and parallel animations ===
  var activeAnimations = {};

  // === UTILITIES ===

  function findTreeNavLink() {
    var selectors = [
      'a[href="/tree"]',
      'a[href="/tree/"]',
      'a[href*="/tree"]',
      '[data-nav="tree"]'
    ];
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (el) return el;
    }
    return null;
  }

  function findMemoryCard(element) {
    if (!element) return null;
    var card = element.closest(".timeline-card");
    if (card) return card;
    card = element.closest("[data-memory-id]");
    if (card) return card;
    card = element.closest(".memory-card");
    if (card) return card;
    // Fallback: walk up to find a reasonably-sized parent
    var el = element;
    for (var i = 0; i < 4 && el.parentElement; i++) {
      el = el.parentElement;
      if (el.offsetWidth > 200) return el;
    }
    return null;
  }

  function getRect(element) {
    if (!element) return null;
    var rect = element.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return null;
    return rect;
  }

  function forceReflow(element) {
    // Reading a layout property forces the browser to compute current position
    // before any CSS transition starts — this is more reliable than rAF
    void element.offsetHeight;
  }

  function cleanupAfter(element, ms) {
    if (!ms) ms = 1200;
    var removed = false;
    function remove() {
      if (removed) return;
      removed = true;
      if (element.parentNode) element.parentNode.removeChild(element);
    }
    element.addEventListener("transitionend", remove, { once: true });
    setTimeout(remove, ms);
  }

  // === ANIMATIONS ===

  function animatePinToTree(btn, callback) {
    var card = findMemoryCard(btn);
    var navLink = findTreeNavLink();
    var cardRect = getRect(card);
    var targetRect = getRect(navLink);

    // Graceful degradation: no elements found → skip animation
    if (!cardRect || !targetRect) {
      if (callback) callback();
      return;
    }

    // Create a simple green circle (more robust than cloneNode which can break layouts)
    var flyEl = document.createElement("div");
    flyEl.style.cssText =
      "position:fixed;" +
      "top:" + (cardRect.top + cardRect.height / 2 - 25) + "px;" +
      "left:" + (cardRect.left + cardRect.width / 2 - 25) + "px;" +
      "width:50px;height:50px;border-radius:50%;" +
      "background:linear-gradient(135deg,#4ade80,#16a34a);" +
      "box-shadow:0 10px 30px rgba(22,163,74,0.4);" +
      "display:flex;align-items:center;justify-content:center;font-size:20px;" +
      "z-index:9999;pointer-events:none;";
    flyEl.textContent = "\uD83C\uDF33";
    document.body.appendChild(flyEl);

    // Dim the original card briefly
    if (card) {
      card.style.transition = "transform 0.3s ease, opacity 0.3s ease";
      card.style.transform = "scale(0.96)";
      card.style.opacity = "0.6";
      setTimeout(function () {
        card.style.transform = "";
        card.style.opacity = "";
      }, 500);
    }

    // Force reflow so the browser registers the initial position
    forceReflow(flyEl);

    var targetX = targetRect.left + targetRect.width / 2 - 20;
    var targetY = targetRect.top + targetRect.height / 2 - 20;

    // Start the fly transition
    flyEl.style.transition = "all 0.6s cubic-bezier(0.34,1.56,0.64,1)";
    flyEl.style.top = targetY + "px";
    flyEl.style.left = targetX + "px";
    flyEl.style.width = "40px";
    flyEl.style.height = "40px";
    flyEl.style.opacity = "0.2";
    flyEl.style.fontSize = "16px";
    flyEl.style.boxShadow = "0 0 20px rgba(22,163,74,0.6)";

    // Pulse on nav link when the element "arrives"
    setTimeout(function () {
      if (navLink) {
        navLink.style.transition = "transform 0.3s ease, text-shadow 0.3s ease";
        navLink.style.transform = "scale(1.2)";
        navLink.style.textShadow = "0 0 12px rgba(22,163,74,0.6)";
        setTimeout(function () {
          navLink.style.transform = "";
          navLink.style.textShadow = "";
        }, 400);
      }
    }, 450);

    cleanupAfter(flyEl, 900);
    setTimeout(function () { if (callback) callback(); }, 700);
  }

  function animateUnpinFromTree(btn, callback) {
    var card = findMemoryCard(btn);
    var navLink = findTreeNavLink();
    var cardRect = getRect(card);
    var sourceRect = getRect(navLink);

    if (!cardRect || !sourceRect) {
      if (callback) callback();
      return;
    }

    // Small green dot that flies from the nav link to the card
    var dot = document.createElement("div");
    dot.style.cssText =
      "position:fixed;" +
      "top:" + (sourceRect.top + sourceRect.height / 2 - 12) + "px;" +
      "left:" + (sourceRect.left + sourceRect.width / 2 - 12) + "px;" +
      "width:24px;height:24px;border-radius:50%;" +
      "background:linear-gradient(135deg,#86efac,#22c55e);" +
      "box-shadow:0 0 15px rgba(22,163,74,0.5);" +
      "display:flex;align-items:center;justify-content:center;font-size:12px;" +
      "z-index:9999;pointer-events:none;";
    dot.textContent = "\uD83C\uDF33";
    document.body.appendChild(dot);

    forceReflow(dot);

    var targetX = cardRect.left + 30;
    var targetY = cardRect.top + cardRect.height / 2 - 12;

    dot.style.transition = "all 0.5s cubic-bezier(0.34,1.56,0.64,1)";
    dot.style.top = targetY + "px";
    dot.style.left = targetX + "px";
    dot.style.opacity = "0";
    dot.style.transform = "scale(0.3)";

    // Card glow when the dot "arrives"
    setTimeout(function () {
      if (card) {
        card.style.transition = "box-shadow 0.4s ease";
        card.style.boxShadow = "0 0 25px rgba(22,163,74,0.25)";
        setTimeout(function () { card.style.boxShadow = ""; }, 500);
      }
    }, 350);

    cleanupAfter(dot, 800);
    setTimeout(function () { if (callback) callback(); }, 600);
  }

  // === MAIN TOGGLE (exposed globally) ===

  window.togglePin = function (btn) {
    if (!btn) return;

    var memoryId = btn.getAttribute("data-memory-id");
    if (!memoryId) return;

    // Prevent double-click / parallel animation for same memory
    if (btn.getAttribute("data-busy") === "true") return;
    if (activeAnimations[memoryId]) return;

    var isPinned = btn.getAttribute("data-is-pinned") === "true";

    // Client-side max-8 check (also enforced server-side)
    if (!isPinned) {
      var counterEl = document.querySelector(".pin-counter");
      if (counterEl) {
        var parts = counterEl.textContent.trim().split("/");
        var current = parseInt(parts[0], 10);
        if (current >= 8) {
          showNotification(STR.maxPinnedAlert);
          return;
        }
      }
    }

    // Lock
    btn.setAttribute("data-busy", "true");
    activeAnimations[memoryId] = true;

    // API call FIRST, animation only on success
    fetch("/memories/" + memoryId + "/toggle-favorite", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" }
    })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      if (data.error === "max_reached") {
        showNotification(STR.maxPinnedAlert);
        unlock();
        return;
      }

      var nowPinned = data.is_favorite;
      var totalPinned = data.total_pinned;

      // Update button state immediately
      btn.setAttribute("data-is-pinned", nowPinned ? "true" : "false");
      btn.title = nowPinned ? STR.unpinFromTree : STR.pinToTree;

      if (nowPinned) {
        btn.classList.remove("bg-stone-100", "text-stone-400", "hover:bg-emerald-50", "hover:text-emerald-600");
        btn.classList.add("bg-emerald-100", "text-emerald-700");
      } else {
        btn.classList.remove("bg-emerald-100", "text-emerald-700");
        btn.classList.add("bg-stone-100", "text-stone-400", "hover:bg-emerald-50", "hover:text-emerald-600");
      }

      // Update all pin counters on the page
      document.querySelectorAll(".pin-counter").forEach(function (el) {
        el.textContent = totalPinned + "/8";
      });

      // Play animation (unlock in callback)
      if (nowPinned) {
        animatePinToTree(btn, unlock);
      } else {
        animateUnpinFromTree(btn, unlock);
      }
    })
    .catch(function (err) {
      console.error("[MemoryTree] Pin toggle failed:", err);
      unlock();
    });

    function unlock() {
      btn.setAttribute("data-busy", "false");
      delete activeAnimations[memoryId];
    }
  };

  // === UNPIN FROM TREE PAGE (fall animation) ===

  window.unpinFromTree = function (memoryId, buttonElement) {
    if (!memoryId) return;
    var key = "tree-" + memoryId;
    if (activeAnimations[key]) return;
    activeAnimations[key] = true;

    // Find the hanging element
    var hangingEl = document.getElementById("pinned-" + memoryId);
    if (!hangingEl && buttonElement) {
      hangingEl = buttonElement.closest(".hanging-memory")
              || buttonElement.closest('[data-memory-id="' + memoryId + '"]');
    }
    if (!hangingEl) {
      console.error("[MemoryTree] Hanging element not found for id:", memoryId);
      delete activeAnimations[key];
      return;
    }

    // API call FIRST
    fetch("/memories/" + memoryId + "/toggle-favorite", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" }
    })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      // Only animate if actually unpinned
      if (!data.is_favorite) {
        playFallAnimation(hangingEl, function () {
          delete activeAnimations[key];
        });
      } else {
        // Was already unpinned and got re-pinned? Unlikely, but handle.
        delete activeAnimations[key];
      }
    })
    .catch(function (err) {
      console.error("[MemoryTree] Unpin failed:", err);
      delete activeAnimations[key];
    });
  };

  function playFallAnimation(element, callback) {
    // 1. "Tear" the thread
    var thread = element.querySelector(".hanging-thread");
    if (thread) {
      thread.style.transition = "opacity 0.15s ease";
      thread.style.opacity = "0";
    }

    // 2. Stop pendulum animation so the fall transition takes over
    element.style.animation = "none";
    element.style.transformOrigin = "top center";

    // 3. Force reflow
    forceReflow(element);

    // 4. Fall
    element.style.transition = "transform 0.8s cubic-bezier(0.55,0,1,0.45), opacity 0.8s ease-out";
    element.style.transform = "translateY(250px) rotate(12deg)";
    element.style.opacity = "0";
    element.style.pointerEvents = "none";

    // 5. Cleanup
    var cleaned = false;
    function cleanup() {
      if (cleaned) return;
      cleaned = true;
      if (element.parentNode) element.parentNode.removeChild(element);
      checkTreeEmptyState();
      if (callback) callback();
    }

    element.addEventListener("transitionend", function handler(e) {
      if (e.target === element) {
        element.removeEventListener("transitionend", handler);
        cleanup();
      }
    });
    // Fallback timeout
    setTimeout(cleanup, 1200);
  }

  function checkTreeEmptyState() {
    var remaining = document.querySelectorAll("#pinned-memories .hanging-memory");
    if (remaining.length === 0) {
      var container = document.getElementById("pinned-memories");
      if (container && !document.getElementById("empty-tree-hint")) {
        var hint = document.createElement("div");
        hint.id = "empty-tree-hint";
        hint.className = "absolute top-1/3 left-1/2 -translate-x-1/2 pointer-events-none text-center";
        hint.style.opacity = "0";
        hint.style.transition = "opacity 0.5s ease";
        hint.innerHTML = '<p class="text-sm text-green-700/60">' + STR.emptyTreeHint + '</p>';
        container.appendChild(hint);
        forceReflow(hint);
        hint.style.opacity = "1";
      }
    }
  }

  // === NOTIFICATION HELPER ===

  function showNotification(message) {
    var existing = document.getElementById("pin-notification");
    if (existing) existing.parentNode.removeChild(existing);

    var notif = document.createElement("div");
    notif.id = "pin-notification";
    notif.textContent = message;
    notif.style.cssText =
      "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);" +
      "background:#1f2937;color:white;padding:12px 24px;border-radius:12px;" +
      "font-size:14px;z-index:10000;box-shadow:0 10px 30px rgba(0,0,0,0.2);" +
      "transition:opacity 0.3s ease;";
    document.body.appendChild(notif);

    setTimeout(function () {
      notif.style.opacity = "0";
      setTimeout(function () {
        if (notif.parentNode) notif.parentNode.removeChild(notif);
      }, 300);
    }, 3000);
  }

})();
