// Reading-difficulty chapter table: the first five chapters, then "Show N
// more", and a filter down to the chapters read above the target. Without
// this script every chapter shows. Listens on the document and re-applies
// after live.js swaps the page in place.
(function () {
  "use strict";

  var SHOWN = 5;

  function apply(table) {
    var rows = table.querySelectorAll(".difficulty-chapter");
    var all = table.dataset.expanded === "1";
    var filter = table.querySelector("[data-difficulty-filter]");
    var onlyAbove = filter && filter.checked;
    var more = table.querySelector(".difficulty-more");
    var button = table.querySelector("[data-difficulty-more]");
    var visible = 0;
    rows.forEach(function (row) {
      var match = !onlyAbove || row.dataset.above === "1";
      var show = match && (all || onlyAbove || visible < SHOWN);
      if (match) visible += 1;
      row.hidden = !show;
    });
    if (more) more.hidden = false;
    if (button) button.hidden = all || onlyAbove;
  }

  function applyAll() {
    document.querySelectorAll("[data-difficulty-table]").forEach(apply);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-difficulty-more]");
    if (!button) return;
    var table = button.closest("[data-difficulty-table]");
    table.dataset.expanded = "1";
    apply(table);
  });

  document.addEventListener("change", function (event) {
    var filter = event.target.closest("[data-difficulty-filter]");
    if (filter) apply(filter.closest("[data-difficulty-table]"));
  });

  document.addEventListener("DOMContentLoaded", applyAll);
  new MutationObserver(applyAll).observe(document.documentElement, { childList: true, subtree: true });
})();
