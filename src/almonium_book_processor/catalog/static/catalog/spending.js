// Spending charts: a tooltip per column, on hover and on keyboard focus. The column carries
// its own figures (data-label, data-total, data-parts "slot|name|value;..."), so nothing is
// computed here; the table under the charts holds every value for readers without a pointer.
(function () {
  "use strict";

  function tipFor(chart) {
    var tip = chart.querySelector(".spend-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "spend-tip";
      tip.hidden = true;
      chart.appendChild(tip);
    }
    return tip;
  }

  function show(column) {
    var chart = column.closest(".spend-chart");
    if (!chart) return;
    var tip = tipFor(chart);
    tip.textContent = "";
    var head = document.createElement("strong");
    head.textContent = column.dataset.label + " · " + column.dataset.total;
    tip.appendChild(head);
    (column.dataset.parts || "").split(";").forEach(function (part) {
      var bits = part.split("|");
      if (bits.length !== 3) return;
      var row = document.createElement("div");
      var name = document.createElement("span");
      var swatch = document.createElement("span");
      swatch.className = "spend-swatch spend-series-" + bits[0];
      name.appendChild(swatch);
      name.appendChild(document.createTextNode(bits[1]));
      var value = document.createElement("span");
      value.textContent = bits[2];
      row.appendChild(name);
      row.appendChild(value);
      tip.appendChild(row);
    });
    tip.hidden = false;
    var box = chart.getBoundingClientRect();
    var mark = column.getBoundingClientRect();
    var left = mark.left - box.left + mark.width / 2 - tip.offsetWidth / 2;
    left = Math.max(8, Math.min(left, box.width - tip.offsetWidth - 8));
    tip.style.left = left + "px";
    tip.style.top = Math.max(8, mark.top - box.top - tip.offsetHeight + 40) + "px";
  }

  function hide(column) {
    var chart = column.closest(".spend-chart");
    var tip = chart && chart.querySelector(".spend-tip");
    if (tip) tip.hidden = true;
  }

  // On a narrow screen the charts scroll sideways: open them on the newest bucket.
  function newestFirst() {
    document.querySelectorAll(".spend-svg-wrap").forEach(function (wrap) {
      wrap.scrollLeft = wrap.scrollWidth;
    });
  }
  if (document.readyState === "complete") newestFirst();
  else window.addEventListener("load", newestFirst);

  ["mouseover", "focusin"].forEach(function (kind) {
    document.addEventListener(kind, function (event) {
      var column = event.target.closest && event.target.closest(".spend-column");
      if (column) show(column);
    });
  });
  ["mouseout", "focusout"].forEach(function (kind) {
    document.addEventListener(kind, function (event) {
      var column = event.target.closest && event.target.closest(".spend-column");
      if (column && !column.contains(event.relatedTarget)) hide(column);
    });
  });
})();
