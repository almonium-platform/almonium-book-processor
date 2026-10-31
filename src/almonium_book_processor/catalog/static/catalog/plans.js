// The plans popover on the dashboard: a limit typed in its field is saved once the owner stops
// typing, and the popover opens again after a save so the change can be seen where it was made.
(function () {
  var timers = new WeakMap();

  document.addEventListener("change", function (event) {
    var field = event.target.closest("[data-submit-on-change]");
    if (!field || !field.form) return;
    clearTimeout(timers.get(field));
    timers.set(field, setTimeout(function () { field.form.requestSubmit(field.form.querySelector("button[value=limit]")); }, 900));
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (location.hash !== "#plans") return;
    var plans = document.getElementById("plans");
    if (plans) plans.open = true;
  });
})();
