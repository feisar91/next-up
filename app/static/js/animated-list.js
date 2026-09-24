// Keyed list renderer: diffs `items` against a container's existing children
// (matched by data-key) so unchanged rows are updated in place, new rows
// animate in, and removed rows animate out - instead of a full innerHTML
// replace snapping the whole list on every live queue update.
window.AnimatedList = (function () {
  function render(container, items, keyFn, createNode, updateNode) {
    const existing = new Map();
    Array.from(container.children).forEach(function (el) {
      if (el.dataset && el.dataset.key) existing.set(el.dataset.key, el);
    });

    let prevEl = null;

    items.forEach(function (item, index) {
      const key = String(keyFn(item, index));
      let el = existing.get(key);

      if (el) {
        existing.delete(key);
        el.classList.remove("anim-exit");
        updateNode(el, item, index);
      } else {
        el = createNode(item, index);
        el.dataset.key = key;
        el.classList.add("anim-enter");
        container.appendChild(el);
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            el.classList.add("anim-enter-active");
          });
        });
      }

      if (prevEl) {
        if (prevEl.nextElementSibling !== el) container.insertBefore(el, prevEl.nextElementSibling);
      } else if (container.firstElementChild !== el) {
        container.insertBefore(el, container.firstElementChild);
      }
      prevEl = el;
    });

    existing.forEach(function (el) {
      el.classList.add("anim-exit");
      let removed = false;
      function remove() {
        if (removed) return;
        removed = true;
        if (el.parentNode) el.parentNode.removeChild(el);
      }
      el.addEventListener("transitionend", remove);
      setTimeout(remove, 300);
    });
  }

  return { render: render };
})();
