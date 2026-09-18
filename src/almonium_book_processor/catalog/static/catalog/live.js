// Follows jobs on an open page so nobody has to reload to see them move.
//
// A page marks the part of itself that jobs change with data-live (the URL of
// its activity endpoint) and data-live-fingerprint (the server's fingerprint
// when it rendered). This polls that URL — quickly while a job is active,
// slowly otherwise, never while the tab is hidden — and when the fingerprint
// differs, fetches the page again and swaps the marked part in place. Open
// panels stay open and a form someone is filling in is never replaced under
// them; the swap waits until they leave it.
(function () {
  "use strict";

  var ACTIVE_INTERVAL = 2500;
  var IDLE_INTERVAL = 12000;
  var RETRY_INTERVAL = 30000;

  var root = document.querySelector("[data-live]");
  if (!root || !window.fetch) return;

  var fingerprint = root.dataset.liveFingerprint || "";
  var timer = null;
  var refreshing = false;
  var pending = false;

  function busy() {
    var active = document.activeElement;
    if (active && root.contains(active) && active.matches("input, textarea, select")) return true;
    return Array.prototype.some.call(root.querySelectorAll("input, textarea, select"), function (field) {
      if (field.tagName === "SELECT") {
        // Without a selected attribute the browser picks the first option, so
        // that, not "no option", is the select's untouched state.
        var wanted = field.multiple ? -1 : 0;
        for (var i = 0; i < field.options.length; i++) {
          if (field.options[i].defaultSelected) { wanted = i; break; }
        }
        return field.selectedIndex !== wanted;
      }
      if (field.type === "checkbox" || field.type === "radio") return field.checked !== field.defaultChecked;
      if (field.type === "hidden" || field.type === "submit" || field.type === "button" || field.type === "file") return false;
      return field.value !== field.defaultValue;
    });
  }

  function openPanels() {
    var state = {};
    root.querySelectorAll("details[id]").forEach(function (panel) { state[panel.id] = panel.open; });
    return state;
  }

  function swap(markup) {
    var fresh = new DOMParser().parseFromString(markup, "text/html").querySelector("[data-live]");
    if (!fresh) return false;
    var state = openPanels();
    fresh.querySelectorAll("details[id]").forEach(function (panel) {
      if (Object.prototype.hasOwnProperty.call(state, panel.id)) panel.open = state[panel.id];
    });
    root.replaceWith(fresh);
    root = fresh;
    fingerprint = root.dataset.liveFingerprint || fingerprint;
    document.dispatchEvent(new CustomEvent("live:refreshed", { detail: { root: root } }));
    return true;
  }

  function refresh() {
    if (refreshing) return;
    if (busy()) { pending = true; return; }
    refreshing = true;
    pending = false;
    fetch(location.href, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok || response.redirected) throw new Error("page unavailable");
        return response.text();
      })
      .then(swap)
      .catch(function () { pending = true; })
      .then(function () { refreshing = false; });
  }

  function poll() {
    timer = null;
    if (document.hidden) return;
    fetch(root.dataset.live, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok || response.redirected) throw new Error("activity unavailable");
        return response.json();
      })
      .then(function (activity) {
        if (activity.fingerprint !== fingerprint || pending) {
          fingerprint = activity.fingerprint;
          refresh();
        }
        schedule(activity.active.length ? ACTIVE_INTERVAL : IDLE_INTERVAL);
      })
      .catch(function () { schedule(RETRY_INTERVAL); });
  }

  function schedule(delay) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(poll, delay);
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) schedule(0);
  });
  // A field someone was sitting in no longer blocks the swap once they leave it.
  document.addEventListener("focusout", function () {
    if (pending) setTimeout(refresh, 0);
  });

  // The first poll is soon whatever the page shows: it learns whether a job is
  // active and paces itself from there.
  schedule(ACTIVE_INTERVAL);
})();
