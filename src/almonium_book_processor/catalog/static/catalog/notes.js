// Reader notes layer: hovering a card lights its quote, clicking a quote or a
// card focuses the card (Edit block, Next), j / k move between cards, and a
// gutter at the right edge marks every card with a box for the viewport.
// Listens on the document and redraws after live.js swaps the page in place.
(function () {
  "use strict";

  function layer() { return document.querySelector("[data-notes-layer]"); }
  function cards() { return Array.prototype.slice.call(document.querySelectorAll(".note-card")); }
  function card(index) { return document.querySelector('.note-card[data-note="' + index + '"]'); }

  function light(index, on) {
    var quote = document.querySelector('.note-quote[data-note="' + index + '"]');
    if (quote) quote.classList.toggle("is-lit", on);
  }

  function focus(target, scroll) {
    if (!target) return;
    cards().forEach(function (other) {
      if (other !== target && other.classList.contains("is-focused")) {
        other.classList.remove("is-focused");
        light(other.dataset.note, false);
      }
    });
    target.classList.add("is-focused");
    light(target.dataset.note, true);
    target.focus({ preventScroll: true });
    if (scroll) {
      var block = target.closest(".notes-block");
      var box = block.getBoundingClientRect();
      if (box.top < 90 || box.bottom > window.innerHeight) block.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function step(delta) {
    var all = cards();
    if (!all.length) return;
    var current = all.findIndex(function (item) { return item.classList.contains("is-focused"); });
    var next = current < 0 ? (delta > 0 ? 0 : all.length - 1) : Math.min(Math.max(current + delta, 0), all.length - 1);
    focus(all[next], true);
  }

  function drawGutter() {
    var root = layer();
    var gutter = root && root.querySelector("[data-notes-gutter]");
    if (!gutter) return;
    var top = root.getBoundingClientRect().top + window.scrollY;
    var height = root.offsetHeight || 1;
    if (!gutter.childElementCount) {
      cards().forEach(function (item) {
        var tick = document.createElement("span");
        tick.dataset.tick = item.dataset.note;
        if (item.classList.contains("note-content")) tick.className = "note-content";
        gutter.appendChild(tick);
      });
      var view = document.createElement("span");
      view.className = "notes-gutter-view";
      gutter.appendChild(view);
    }
    gutter.querySelectorAll("[data-tick]").forEach(function (tick) {
      var item = card(tick.dataset.tick);
      var offset = item.closest(".notes-block").getBoundingClientRect().top + window.scrollY - top;
      tick.style.top = Math.min(Math.max(offset / height, 0), 1) * 100 + "%";
    });
    var view = gutter.querySelector(".notes-gutter-view");
    var start = (window.scrollY - top) / height;
    var span = window.innerHeight / height;
    view.style.top = Math.min(Math.max(start, 0), 1) * 100 + "%";
    view.style.height = Math.max(Math.min(span, 1 - Math.max(start, 0)), 0) * 100 + "%";
  }

  document.addEventListener("mouseover", function (event) {
    var item = event.target.closest(".note-card");
    if (item) light(item.dataset.note, true);
  });
  document.addEventListener("mouseout", function (event) {
    var item = event.target.closest(".note-card");
    if (item && !item.classList.contains("is-focused") && !item.contains(event.relatedTarget)) light(item.dataset.note, false);
  });

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-note-next]")) { step(1); return; }
    var edit = event.target.closest("[data-note-edit]");
    if (edit) {
      var drawer = edit.closest(".notes-block").querySelector(".reader-drawer");
      drawer.open = true;
      drawer.querySelector("textarea").focus();
      return;
    }
    var tick = event.target.closest("[data-tick]");
    if (tick) { focus(card(tick.dataset.tick), true); return; }
    var target = event.target.closest(".note-card, .note-quote");
    if (target) focus(card(target.dataset.note), target.classList.contains("note-quote"));
  });

  document.addEventListener("keydown", function (event) {
    if (!layer() || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.target.closest("input, textarea, select")) return;
    if (event.key === "j") step(1);
    else if (event.key === "k") step(-1);
  });

  window.addEventListener("scroll", drawGutter, { passive: true });
  window.addEventListener("resize", drawGutter);
  document.addEventListener("DOMContentLoaded", function () {
    drawGutter();
    if (location.hash === "#notes-first") step(1);
  });
  new MutationObserver(function () {
    var gutter = document.querySelector("[data-notes-gutter]");
    if (gutter && !gutter.childElementCount) drawGutter();
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
