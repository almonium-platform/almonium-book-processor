// Reader toolbar and provenance: a select marked data-autosubmit opens its
// choice at once, and a data-copy button puts its value on the clipboard.
// Both listen on the document, so they survive live.js swapping the page.
(function () {
  "use strict";

  document.addEventListener("change", function (event) {
    var select = event.target.closest("select[data-autosubmit]");
    if (select && select.form) select.form.submit();
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-copy]");
    if (!button || !navigator.clipboard) return;
    navigator.clipboard.writeText(button.dataset.copy).then(function () {
      var label = button.textContent;
      button.textContent = "Copied";
      setTimeout(function () { button.textContent = label; }, 1200);
    });
  });
})();
