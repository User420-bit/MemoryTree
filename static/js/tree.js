// Memory Tree — D3.js organische Baum-Visualisierung
// Lädt Erinnerungen via JSON-API und rendert einen interaktiven Baum

(function () {
  "use strict";

  // ── Kategorie-Konfiguration ─────────────────────────────────────────────
  var CATEGORIES = {
    Urlaub:      { emoji: "🏖️", color: "#0d9488", leafFill: "#99f6e4", leafStroke: "#14b8a6" },
    Meilenstein: { emoji: "🌟", color: "#d97706", leafFill: "#fde68a", leafStroke: "#f59e0b" },
    Feier:       { emoji: "🎉", color: "#7c3aed", leafFill: "#ddd6fe", leafStroke: "#8b5cf6" },
    Alltag:      { emoji: "📸", color: "#16a34a", leafFill: "#bbf7d0", leafStroke: "#22c55e" },
    Abenteuer:   { emoji: "🌯", color: "#ea580c", leafFill: "#fed7aa", leafStroke: "#f97316" },
    Besonderes:  { emoji: "❤️", color: "#e11d48", leafFill: "#fecdd3", leafStroke: "#f43f5e" }
  };

  var CAT_ORDER = ["Urlaub", "Meilenstein", "Feier", "Alltag", "Abenteuer", "Besonderes"];

  // ── State ───────────────────────────────────────────────────────────────
  var allMemories = [];
  var activeCategory = "all";
  var activeYear = "all";
  var favOnly = false;

  // ── DOM refs ────────────────────────────────────────────────────────────
  var container = document.getElementById("memory-tree-container");
  var svgEl = document.getElementById("memory-tree");
  var tooltip = document.getElementById("tree-tooltip");
  var ttTitle = document.getElementById("tt-title");
  var ttDate = document.getElementById("tt-date");
  var ttCategory = document.getElementById("tt-category");
  var ttLocation = document.getElementById("tt-location");
  var ttPhoto = document.getElementById("tt-photo");

  // ── Daten laden ─────────────────────────────────────────────────────────
  function loadMemories() {
    return fetch("/memories", {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      allMemories = data;
      populateYearFilter();
      renderTree();
    })
    .catch(function (err) {
      console.error("Fehler beim Laden der Erinnerungen:", err);
    });
  }

  // ── Year-Filter befüllen ────────────────────────────────────────────────
  function populateYearFilter() {
    var years = {};
    allMemories.forEach(function (m) {
      var y = m.date ? m.date.substring(0, 4) : null;
      if (y) years[y] = true;
    });
    var sel = document.getElementById("year-filter");
    var sorted = Object.keys(years).sort().reverse();
    sorted.forEach(function (y) {
      var opt = document.createElement("option");
      opt.value = y;
      opt.textContent = y;
      sel.appendChild(opt);
    });
  }

  // ── Filter anwenden ─────────────────────────────────────────────────────
  function getFiltered() {
    return allMemories.filter(function (m) {
      if (activeCategory !== "all" && m.category !== activeCategory) return false;
      if (activeYear !== "all" && (!m.date || m.date.substring(0, 4) !== activeYear)) return false;
      if (favOnly && !m.is_favorite) return false;
      return true;
    });
  }

  // ── Hierarchie bauen ───────────────────────────────────────────────────
  function buildHierarchy(memories) {
    var grouped = {};
    CAT_ORDER.forEach(function (c) { grouped[c] = []; });
    memories.forEach(function (m) {
      var cat = m.category || "Alltag";
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(m);
    });

    var children = [];
    CAT_ORDER.forEach(function (cat) {
      var items = grouped[cat];
      if (items.length === 0 && activeCategory !== "all") return;
      var catChildren = items.map(function (m) {
        return {
          name: m.title,
          memory: m,
          category: cat
        };
      });
      children.push({
        name: cat,
        category: cat,
        children: catChildren
      });
    });

    return {
      name: "root",
      children: children
    };
  }

  // ── Rendering ──────────────────────────────────────────────────────────
  function renderTree() {
    var filtered = getFiltered();
    var root = buildHierarchy(filtered);

    var W = container.clientWidth;
    var H = Math.max(container.clientHeight, 600);

    // Clear SVG
    d3.select(svgEl).selectAll("*").remove();
    svgEl.setAttribute("width", W);
    svgEl.setAttribute("height", H);

    var svg = d3.select(svgEl);

    // Zoom group
    var g = svg.append("g");
    var zoom = d3.zoom()
      .scaleExtent([0.4, 3])
      .on("zoom", function (event) {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);

    // Ground
    var groundY = H - 60;
    g.append("rect")
      .attr("x", 0).attr("y", groundY)
      .attr("width", W).attr("height", 60)
      .attr("fill", "url(#groundGrad)");

    // Gradients
    var defs = svg.append("defs");

    // Ground gradient
    var gg = defs.append("linearGradient").attr("id", "groundGrad").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 1);
    gg.append("stop").attr("offset", "0%").attr("stop-color", "#8B7355");
    gg.append("stop").attr("offset", "100%").attr("stop-color", "#6B5340");

    // Trunk gradient
    var tg = defs.append("linearGradient").attr("id", "trunkGrad").attr("x1", 0).attr("y1", 0).attr("x2", 1).attr("y2", 0);
    tg.append("stop").attr("offset", "0%").attr("stop-color", "#5C4033");
    tg.append("stop").attr("offset", "50%").attr("stop-color", "#8B6914");
    tg.append("stop").attr("offset", "100%").attr("stop-color", "#5C4033");

    // Leaf glow filter
    var glowFilter = defs.append("filter").attr("id", "favGlow");
    glowFilter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "blur");
    glowFilter.append("feMerge").selectAll("feMergeNode").data(["blur", "SourceGraphic"])
      .enter().append("feMergeNode").attr("in", function(d){return d;});

    if (filtered.length === 0) {
      renderEmptyState(g, W, H, groundY);
      return;
    }

    // Tree layout
    var hierarchy = d3.hierarchy(root);
    var treeW = Math.min(W - 100, 900);
    var treeH = groundY - 120;

    var treeLayout = d3.tree().size([treeW, treeH]);
    treeLayout(hierarchy);

    // Center the tree horizontally
    var offsetX = (W - treeW) / 2;
    var offsetY = 60;

    // Invert Y: root at bottom (ground level)
    hierarchy.each(function (d) {
      d.renderX = offsetX + d.x;
      d.renderY = groundY - 30 - d.y; // invert: root at bottom
    });

    // Draw trunk (root to ground)
    var rootNode = hierarchy;
    var trunkX = rootNode.renderX;
    var trunkTopY = rootNode.renderY;

    // Organic trunk path
    g.append("path")
      .attr("d", function () {
        var bw = 18;
        return "M" + (trunkX - bw) + "," + groundY +
               " C" + (trunkX - bw - 5) + "," + (groundY - 40) +
               " " + (trunkX - bw + 3) + "," + (trunkTopY + 30) +
               " " + (trunkX - 6) + "," + trunkTopY +
               " L" + (trunkX + 6) + "," + trunkTopY +
               " C" + (trunkX + bw - 3) + "," + (trunkTopY + 30) +
               " " + (trunkX + bw + 5) + "," + (groundY - 40) +
               " " + (trunkX + bw) + "," + groundY +
               " Z";
      })
      .attr("fill", "url(#trunkGrad)");

    // Roots
    [-25, -12, 12, 25].forEach(function (dx) {
      g.append("path")
        .attr("d", "M" + trunkX + "," + groundY +
              " Q" + (trunkX + dx * 1.5) + "," + (groundY + 10) +
              " " + (trunkX + dx * 2.5) + "," + (groundY + 25))
        .attr("fill", "none")
        .attr("stroke", "#6B5340")
        .attr("stroke-width", 3)
        .attr("stroke-linecap", "round")
        .attr("opacity", 0.6);
    });

    // Partner-since label at trunk
    var partnerSince = window.__PARTNER_SINCE__ || "";
    if (partnerSince) {
      var parts = partnerSince.split("-");
      var label = "Zusammen seit " + parts[2] + "." + parts[1] + "." + parts[0];
      g.append("text")
        .attr("x", trunkX)
        .attr("y", groundY - 10)
        .attr("text-anchor", "middle")
        .attr("fill", "#fef3c7")
        .attr("font-size", "11px")
        .attr("font-weight", "600")
        .text(label);
    }

    // Draw branches (links)
    var links = hierarchy.links().filter(function (l) {
      return l.source.depth >= 0; // all links
    });

    links.forEach(function (link) {
      var s = link.source;
      var t = link.target;
      var cat = t.data.category || (t.parent && t.parent.data.category) || "Alltag";
      var conf = CATEGORIES[cat] || CATEGORIES.Alltag;

      var depth = t.depth;
      var strokeW = depth === 1 ? 8 : (depth === 2 ? 3 : 2);
      var branchColor = depth === 1 ? "#6B5340" : conf.color;

      // Curved branch path
      var midY = (s.renderY + t.renderY) / 2;
      var path = "M" + s.renderX + "," + s.renderY +
                 " C" + s.renderX + "," + midY +
                 " " + t.renderX + "," + midY +
                 " " + t.renderX + "," + t.renderY;

      g.append("path")
        .attr("class", "branch-path")
        .attr("d", path)
        .attr("stroke", branchColor)
        .attr("stroke-width", strokeW)
        .attr("opacity", depth === 1 ? 0.8 : 0.5);
    });

    // Draw category labels at branch nodes
    hierarchy.children.forEach(function (catNode) {
      var cat = catNode.data.category || catNode.data.name;
      var conf = CATEGORIES[cat] || CATEGORIES.Alltag;
      g.append("text")
        .attr("x", catNode.renderX)
        .attr("y", catNode.renderY - 12)
        .attr("text-anchor", "middle")
        .attr("fill", conf.color)
        .attr("font-size", "12px")
        .attr("font-weight", "bold")
        .text(conf.emoji + " " + cat);
    });

    // Draw leaf nodes (memories)
    var leaves = hierarchy.leaves().filter(function (d) { return d.data.memory; });

    leaves.forEach(function (leaf) {
      var m = leaf.data.memory;
      var cat = leaf.data.category || "Alltag";
      var conf = CATEGORIES[cat] || CATEGORIES.Alltag;
      var r = m.is_favorite ? 14 : 10;
      var numPhotos = (m.photos && m.photos.length) || 0;
      if (numPhotos > 0) r += 2;

      var leafG = g.append("g")
        .attr("class", "leaf-group")
        .attr("transform", "translate(" + leaf.renderX + "," + leaf.renderY + ")");

      // Leaf circle
      var circle = leafG.append("circle")
        .attr("class", "leaf-node")
        .attr("r", r)
        .attr("fill", conf.leafFill)
        .attr("stroke", conf.leafStroke)
        .attr("stroke-width", 2);

      if (m.is_favorite) {
        circle.attr("filter", "url(#favGlow)");
        // Favorite heart indicator
        leafG.append("text")
          .attr("text-anchor", "middle")
          .attr("dominant-baseline", "central")
          .attr("font-size", "10px")
          .attr("fill", "#e11d48")
          .attr("pointer-events", "none")
          .text("♥");
      }

      // Hover & click events
      leafG
        .on("mouseenter", function (event) {
          showTooltip(event, m, cat);
          d3.select(this).select("circle").transition().duration(150).attr("r", r + 4);
        })
        .on("mouseleave", function () {
          hideTooltip();
          d3.select(this).select("circle").transition().duration(150).attr("r", r);
        })
        .on("click", function () {
          window.location.href = "/memories/" + m.id;
        });
    });

    // Grass tufts on ground
    for (var i = 0; i < 30; i++) {
      var gx = Math.random() * W;
      var gh = 8 + Math.random() * 12;
      g.append("line")
        .attr("x1", gx).attr("y1", groundY)
        .attr("x2", gx + (Math.random() - 0.5) * 6).attr("y2", groundY - gh)
        .attr("stroke", "#4ade80")
        .attr("stroke-width", 1.5)
        .attr("opacity", 0.4 + Math.random() * 0.3);
    }
  }

  // ── Empty state ─────────────────────────────────────────────────────────
  function renderEmptyState(g, W, H, groundY) {
    var cx = W / 2;
    // Small sapling
    g.append("line")
      .attr("x1", cx).attr("y1", groundY)
      .attr("x2", cx).attr("y2", groundY - 80)
      .attr("stroke", "#8B6914")
      .attr("stroke-width", 4)
      .attr("stroke-linecap", "round");

    // Two tiny leaves
    g.append("circle")
      .attr("cx", cx - 12).attr("cy", groundY - 85)
      .attr("r", 8).attr("fill", "#86efac").attr("opacity", 0.8);
    g.append("circle")
      .attr("cx", cx + 12).attr("cy", groundY - 90)
      .attr("r", 8).attr("fill", "#86efac").attr("opacity", 0.8);

    g.append("text")
      .attr("x", cx).attr("y", groundY - 120)
      .attr("text-anchor", "middle")
      .attr("fill", "#57534e")
      .attr("font-size", "16px")
      .attr("font-weight", "600")
      .text("Pflanze eure erste Erinnerung 🌱");

    g.append("text")
      .attr("x", cx).attr("y", groundY - 100)
      .attr("text-anchor", "middle")
      .attr("fill", "#a8a29e")
      .attr("font-size", "13px")
      .text("Klicke oben auf „Neue Erinnerung"");
  }

  // ── Tooltip ─────────────────────────────────────────────────────────────
  function showTooltip(event, m, cat) {
    var conf = CATEGORIES[cat] || CATEGORIES.Alltag;
    ttTitle.textContent = m.title;
    ttCategory.textContent = conf.emoji + " " + cat;
    ttCategory.style.color = conf.color;
    ttDate.textContent = formatDate(m.date);
    ttLocation.textContent = m.location ? "📍 " + m.location : "";
    ttLocation.style.display = m.location ? "block" : "none";

    // Photo thumbnail
    if (m.photos && m.photos.length > 0) {
      ttPhoto.src = "/" + m.photos[0].filepath;
      ttPhoto.classList.remove("hidden");
    } else {
      ttPhoto.classList.add("hidden");
    }

    // Position tooltip
    var rect = container.getBoundingClientRect();
    var x = event.pageX - rect.left - window.scrollX + 15;
    var y = event.pageY - rect.top - window.scrollY - 10;
    // Keep within bounds
    if (x + 230 > rect.width) x = x - 250;
    if (y < 0) y = 10;

    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
    tooltip.classList.add("visible");
  }

  function hideTooltip() {
    tooltip.classList.remove("visible");
  }

  function formatDate(isoDate) {
    if (!isoDate) return "";
    var parts = isoDate.split("-");
    return parts[2] + "." + parts[1] + "." + parts[0];
  }

  // ── Filter-Event-Handler ────────────────────────────────────────────────
  function setupFilters() {
    // Category filters
    document.querySelectorAll("#tree-filters .filter-btn[data-category]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll("#tree-filters .filter-btn[data-category]").forEach(function (b) {
          b.classList.remove("active", "ring-2", "ring-emerald-400");
        });
        btn.classList.add("active", "ring-2", "ring-emerald-400");
        activeCategory = btn.dataset.category;
        renderTree();
      });
    });

    // Year filter
    document.getElementById("year-filter").addEventListener("change", function (e) {
      activeYear = e.target.value;
      renderTree();
    });

    // Favorites filter
    var favBtn = document.getElementById("fav-filter");
    if (favBtn) {
      favBtn.addEventListener("click", function () {
        favOnly = !favOnly;
        favBtn.dataset.active = favOnly ? "true" : "false";
        if (favOnly) {
          favBtn.classList.add("ring-2", "ring-rose-400", "bg-rose-50");
        } else {
          favBtn.classList.remove("ring-2", "ring-rose-400", "bg-rose-50");
        }
        renderTree();
      });
    }
  }

  // ── Resize handler ──────────────────────────────────────────────────────
  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderTree, 200);
  });

  // ── Init ────────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    setupFilters();
    loadMemories();
  });

})();
