// Reading-difficulty chapter table: the first five chapters, then "Show N
// more", and filter chips down to the chapters read above or below the
// target. A link in the gate callout selects the above filter, opens the
// chapter and scrolls to it. Without this script every chapter shows.
// Listens on the document and re-applies after live.js swaps the page in place.
(function () {
  "use strict";

  var SHOWN = 5;

  function apply(table) {
    var rows = table.querySelectorAll(".difficulty-chapter");
    var all = table.dataset.expanded === "1";
    var filter = table.dataset.filter || "all";
    var more = table.querySelector(".difficulty-more");
    var button = table.querySelector("[data-difficulty-more]");
    var visible = 0;
    rows.forEach(function (row) {
      var match = filter === "all" || row.dataset[filter] === "1";
      var show = match && (all || filter !== "all" || visible < SHOWN);
      if (match) visible += 1;
      row.hidden = !show;
    });
    table.querySelectorAll("[data-difficulty-filter]").forEach(function (chip) {
      chip.classList.toggle("is-active", chip.dataset.difficultyFilter === filter);
    });
    if (more) more.hidden = all || filter !== "all";
    if (button) button.hidden = all || filter !== "all";
  }

  function applyAll() {
    document.querySelectorAll("[data-difficulty-table]").forEach(apply);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-difficulty-more]");
    if (button) {
      var table = button.closest("[data-difficulty-table]");
      table.dataset.expanded = "1";
      apply(table);
      return;
    }
    var chip = event.target.closest("[data-difficulty-filter]");
    if (chip) {
      var chips = chip.closest("[data-difficulty-table]");
      chips.dataset.filter = chip.dataset.difficultyFilter;
      apply(chips);
      return;
    }
    var jump = event.target.closest("[data-difficulty-jump]");
    if (!jump) return;
    var row = document.getElementById(jump.getAttribute("href").slice(1));
    if (!row) return;
    event.preventDefault();
    var target = row.closest("[data-difficulty-table]");
    target.dataset.filter = target.querySelector('[data-difficulty-filter="above"]') ? "above" : "all";
    target.dataset.expanded = "1";
    apply(target);
    row.open = true;
    row.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.addEventListener("DOMContentLoaded", applyAll);
  new MutationObserver(applyAll).observe(document.documentElement, { childList: true, subtree: true });
})();
