// Prices on paid buttons: keep them in step with the form, and ask before a
// large spend.
//
// A button whose price depends on a choice in its form (the chapter to pilot,
// the translation tier) carries data-cost-from, the ids of those fields, and
// data-costs, a price per choice keyed by their values joined with "|". A
// button with data-confirm asks that question before its form submits. Both
// listen on the document, so they survive live.js swapping the page in place.
(function () {
  "use strict";

  function price(button) {
    var costs;
    try { costs = JSON.parse(button.dataset.costs || "{}"); } catch (error) { return; }
    var key = button.dataset.costFrom.split(" ").map(function (id) {
      var field = document.getElementById(id);
      return field ? field.value : "";
    }).join("|");
    var cost = costs[key];
    var label = button.querySelector(".cost-value");
    if (!cost || !label) return;
    label.textContent = cost.label;
    button.title = cost.note;
    if (cost.confirm) button.dataset.confirm = cost.confirm;
    else delete button.dataset.confirm;
  }

  function priceAll() {
    document.querySelectorAll("button[data-cost-from]").forEach(price);
  }

  document.addEventListener("change", function (event) {
    if (!event.target.id) return;
    document.querySelectorAll("button[data-cost-from]").forEach(function (button) {
      if (button.dataset.costFrom.split(" ").indexOf(event.target.id) >= 0) price(button);
    });
  });

  document.addEventListener("submit", function (event) {
    var button = event.submitter;
    if (button && button.dataset.confirm && !window.confirm(button.dataset.confirm)) {
      event.preventDefault();
    }
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", priceAll);
  else priceAll();
})();
