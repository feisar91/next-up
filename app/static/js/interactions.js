(function () {
  function ensureModal() {
    let overlay = document.getElementById("confirm-modal-overlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "confirm-modal-overlay";
    overlay.className = "modal-backdrop";
    overlay.innerHTML =
      '<div class="modal" role="alertdialog" aria-modal="true">' +
      '<p class="modal-message"></p>' +
      '<div class="modal-fields"></div>' +
      '<div class="modal-actions">' +
      '<button type="button" class="btn btn-secondary modal-cancel">Cancel</button>' +
      '<button type="button" class="btn modal-confirm">Confirm</button>' +
      "</div>" +
      "</div>";
    document.body.appendChild(overlay);
    return overlay;
  }

  // options.fields: a <template> whose inputs are shown in the dialog.
  // options.values: {name: value} to pre-fill those inputs.
  // options.confirmLabel: text for the confirm button (default "Confirm").
  // Resolves false on cancel, otherwise {name: value} for the dialog's inputs.
  function showConfirm(message, options) {
    options = options || {};
    return new Promise(function (resolve) {
      const overlay = ensureModal();
      overlay.querySelector(".modal-message").textContent = message;

      const fields = overlay.querySelector(".modal-fields");
      fields.innerHTML = "";
      if (options.fields) fields.appendChild(options.fields.content.cloneNode(true));
      const values = options.values || {};
      fields.querySelectorAll("[name]").forEach(function (input) {
        if (values[input.name] !== undefined) input.value = values[input.name];
      });

      const confirmBtn = overlay.querySelector(".modal-confirm");
      const cancelBtn = overlay.querySelector(".modal-cancel");
      confirmBtn.textContent = options.confirmLabel || "Confirm";

      function cleanup(result) {
        overlay.classList.remove("open");
        confirmBtn.removeEventListener("click", onConfirm);
        cancelBtn.removeEventListener("click", onCancel);
        overlay.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKey);
        resolve(result);
      }
      function onConfirm() {
        const result = {};
        fields.querySelectorAll("[name]").forEach(function (input) {
          result[input.name] = input.value;
        });
        cleanup(result);
      }
      function onCancel() {
        cleanup(false);
      }
      function onBackdrop(e) {
        if (e.target === overlay) cleanup(false);
      }
      function onKey(e) {
        if (e.key === "Escape") cleanup(false);
      }

      confirmBtn.addEventListener("click", onConfirm);
      cancelBtn.addEventListener("click", onCancel);
      overlay.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKey);

      overlay.classList.add("open");
      (fields.querySelector("select, input") || confirmBtn).focus();
    });
  }

  function setLoading(form) {
    const btn = form.querySelector("button[type=submit]");
    if (btn && !btn.disabled) {
      btn.disabled = true;
      btn.classList.add("is-loading");
    }
  }

  // Any form can opt into a custom (non-blocking, on-brand) confirmation
  // instead of window.confirm() by setting data-confirm="message text".
  // Optional: data-confirm-label="Button text", and data-confirm-fields="#template-id"
  // to ask for extra values in the dialog. Those are pre-filled from, and written
  // back to, the form's own inputs with the same names (usually hidden inputs).
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;

    if (form.dataset.confirm && !form.dataset.confirmed) {
      e.preventDefault();
      const values = {};
      Array.from(form.elements).forEach(function (input) {
        if (input.name) values[input.name] = input.value;
      });
      const options = {
        confirmLabel: form.dataset.confirmLabel,
        fields: form.dataset.confirmFields ? document.querySelector(form.dataset.confirmFields) : null,
        values: values,
      };
      showConfirm(form.dataset.confirm, options).then(function (result) {
        if (result) {
          Object.keys(result).forEach(function (name) {
            if (form.elements[name]) form.elements[name].value = result[name];
          });
          form.dataset.confirmed = "1";
          setLoading(form);
          form.submit();
        }
      });
      return;
    }

    setLoading(form);
  });

  // Any element with data-copy="value" becomes a one-click clipboard button.
  document.addEventListener("click", function (e) {
    const el = e.target.closest("[data-copy]");
    if (!el) return;

    const value = el.dataset.copy;
    const originalText = el.textContent;

    function showCopied() {
      el.textContent = "Copied!";
      setTimeout(function () {
        el.textContent = originalText;
      }, 1200);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(showCopied, showCopied);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      showCopied();
    }
  });

  window.showConfirm = showConfirm;
})();
