// Reader toolbar, block editing and provenance.
//
// A select marked data-autosubmit opens its choice at once, and a data-copy
// button puts its value on the clipboard. The chapter select shows a short
// label while closed and the full titles in its list. Edit replaces a block's
// text in place with a textarea as tall as its content; Save stays disabled
// until the text differs and a reason is given, and Cancel or Esc restores it.
// Provenance opens as a popover. Everything listens on the document, so it
// survives live.js swapping the page.
(function () {
  "use strict";

  // Chapter select: short while closed, full titles while choosing.
  function labels(select, full) {
    Array.prototype.forEach.call(select.options, function (option) {
      if (!option.dataset.short) return;
      if (!option.dataset.full) option.dataset.full = option.textContent;
      option.textContent = full || !option.selected ? option.dataset.full : option.dataset.short;
    });
  }
  function shortenAll() {
    document.querySelectorAll("select[data-short-labels]").forEach(function (select) { labels(select, false); });
  }
  ["mousedown", "keydown", "focusin"].forEach(function (type) {
    document.addEventListener(type, function (event) {
      var select = event.target.closest && event.target.closest("select[data-short-labels]");
      if (select) labels(select, true);
    });
  });
  document.addEventListener("focusout", function (event) {
    var select = event.target.closest && event.target.closest("select[data-short-labels]");
    if (select) labels(select, false);
  });

  document.addEventListener("change", function (event) {
    var select = event.target.closest("select[data-autosubmit]");
    if (select && select.form) select.form.submit();
  });

  // Editing in place.
  function fit(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = textarea.scrollHeight + 3 + "px";
  }
  function editorParts(scope) {
    var editor = scope.querySelector("[data-editor]");
    return {
      scope: scope,
      row: scope.closest(".reader-row, .notes-block"),
      view: scope.querySelector("[data-editor-view]"),
      editor: editor,
      text: editor.querySelector("[data-editor-text]"),
      reason: editor.querySelector("[data-editor-reason]"),
      save: editor.querySelector("[data-editor-save]"),
    };
  }
  function refresh(parts) {
    parts.save.disabled = parts.text.value === parts.text.defaultValue || !parts.reason.value.trim();
  }
  function open(id) {
    var scope = document.querySelector('[data-edit-scope="' + id + '"]');
    if (!scope) return;
    var parts = editorParts(scope);
    parts.view.hidden = true;
    parts.editor.hidden = false;
    if (parts.row) parts.row.classList.add("is-editing");
    fit(parts.text);
    refresh(parts);
    parts.text.focus();
    parts.text.setSelectionRange(parts.text.value.length, parts.text.value.length);
  }
  function close(scope) {
    var parts = editorParts(scope);
    parts.text.value = parts.text.defaultValue;
    parts.reason.value = "";
    parts.editor.querySelectorAll(".reader-remove").forEach(function (remove) { remove.open = false; });
    parts.editor.hidden = true;
    parts.view.hidden = false;
    if (parts.row) {
      parts.row.classList.remove("is-editing");
      parts.row.focus({ preventScroll: true });
    }
  }

  document.addEventListener("input", function (event) {
    var scope = event.target.closest("[data-edit-scope]");
    if (!scope || !event.target.closest("[data-editor]")) return;
    var parts = editorParts(scope);
    if (event.target === parts.text) fit(parts.text);
    refresh(parts);
  });

  // Provenance popovers.
  function closePopovers(except) {
    document.querySelectorAll("[data-provenance-toggle][aria-expanded='true']").forEach(function (toggle) {
      if (toggle === except) return;
      toggle.setAttribute("aria-expanded", "false");
      var row = toggle.closest(".reader-row");
      row.querySelector("[data-provenance]").hidden = true;
      row.classList.remove("has-popover");
    });
  }

  document.addEventListener("click", function (event) {
    var copy = event.target.closest("button[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(copy.dataset.copy).then(function () {
        var label = copy.textContent;
        copy.textContent = "Copied";
        setTimeout(function () { copy.textContent = label; }, 1200);
      });
      return;
    }
    var edit = event.target.closest("[data-edit]");
    if (edit) { closePopovers(); open(edit.dataset.edit); return; }
    var cancel = event.target.closest("[data-editor-cancel]");
    if (cancel) { close(cancel.closest("[data-edit-scope]")); return; }
    var toggle = event.target.closest("[data-provenance-toggle]");
    if (toggle) {
      var row = toggle.closest(".reader-row");
      var opening = toggle.getAttribute("aria-expanded") !== "true";
      closePopovers(toggle);
      toggle.setAttribute("aria-expanded", opening ? "true" : "false");
      row.querySelector("[data-provenance]").hidden = !opening;
      row.classList.toggle("has-popover", opening);
      return;
    }
    if (!event.target.closest("[data-provenance]")) closePopovers();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var scope = event.target.closest && event.target.closest("[data-edit-scope]");
    if (scope && event.target.closest("[data-editor]")) { close(scope); return; }
    closePopovers();
  });

  document.addEventListener("DOMContentLoaded", shortenAll);
  new MutationObserver(function () {
    var select = document.querySelector("select[data-short-labels]");
    if (select && !select.querySelector("option[data-full]")) shortenAll();
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
