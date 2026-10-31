// The plans popover on the dashboard: a limit typed in its field is saved once the owner stops
// typing, the popover opens again after a save so the change can be seen where it was made, and
// it closes on Escape or a click outside it.
(function () {
  var timers = new WeakMap();

  document.addEventListener("change", function (event) {
    var field = event.target.closest("[data-submit-on-change]");
    if (!field || !field.form) return;
    clearTimeout(timers.get(field));
    timers.set(field, setTimeout(function () { field.form.requestSubmit(field.form.querySelector("button[value=limit]")); }, 900));
  });

  // Like any popover: Escape or a click outside it closes it.
  function closePlans() {
    var plans = document.getElementById("plans");
    if (!plans || !plans.open) return false;
    plans.open = false;
    return true;
  }

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var plans = document.getElementById("plans");
    // an open date field inside closes first; the next Escape closes the popover
    var inner = plans && plans.querySelector("details[open]");
    if (inner) { inner.open = false; return; }
    if (closePlans()) plans.querySelector("summary").focus();
  });

  document.addEventListener("click", function (event) {
    var plans = document.getElementById("plans");
    if (plans && plans.open && !plans.contains(event.target)) closePlans();
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (location.hash !== "#plans") return;
    var plans = document.getElementById("plans");
    if (plans) plans.open = true;
  });
})();
