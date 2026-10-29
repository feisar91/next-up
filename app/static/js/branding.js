// Admin > Branding: shows the picked colours and name on a small preview as you
// change them, before saving.
(function () {
  const form = document.getElementById("branding-form");
  if (!form) return;
  const preview = document.getElementById("brand-preview");
  const previewName = document.getElementById("brand-preview-name");
  const name = form.elements.name;
  const dark = form.elements.dark;
  const accent = form.elements.accent;

  function update() {
    preview.style.setProperty("--preview-dark", dark.value);
    preview.style.setProperty("--preview-accent", accent.value);
    previewName.textContent = name.value;
  }

  [name, dark, accent].forEach(function (input) {
    input.addEventListener("input", update);
  });

  const reset = form.querySelector("[data-brand-reset]");
  reset.addEventListener("click", function () {
    dark.value = reset.dataset.dark;
    accent.value = reset.dataset.accent;
    update();
  });

  update();
})();
