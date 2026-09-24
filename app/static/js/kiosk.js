// Keeps the "preferred barber" chip list in sync with who's actually on duty,
// so a barber logging in at this location shows up here without a page reload.
(function () {
  const socket = io({ path: "/updates" });
  const group = document.getElementById("barber-chip-group");
  if (!group) return;

  socket.on("connect", function () {
    socket.emit("join", { location: window.LOCATION_SLUG, token: window.KIOSK_TOKEN });
  });

  socket.on("barbers_update", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    renderBarbers(state.barbers);
  });

  function renderBarbers(barbers) {
    const selected = group.querySelector(".barber-chip-input:checked");
    const selectedId = selected ? selected.dataset.barberId : null;
    const nextIds = new Set(barbers.map(function (b) { return String(b.id); }));

    Array.from(group.querySelectorAll("[data-barber-id]")).forEach(function (node) {
      if (!nextIds.has(node.dataset.barberId)) node.remove();
    });

    const presentIds = new Set(
      Array.from(group.querySelectorAll("input[data-barber-id]")).map(function (n) {
        return n.dataset.barberId;
      })
    );

    barbers.forEach(function (barber) {
      const id = String(barber.id);
      if (presentIds.has(id)) {
        // Already shown: pick up display-name changes and keep the server's
        // (alphabetical) order. Re-appending moves the nodes and keeps selection.
        const existingInput = group.querySelector('input[data-barber-id="' + id + '"]');
        const existingLabel = group.querySelector('label[data-barber-id="' + id + '"]');
        if (existingLabel.textContent !== barber.name) existingLabel.textContent = barber.name;
        group.appendChild(existingInput);
        group.appendChild(existingLabel);
        return;
      }

      const input = document.createElement("input");
      input.type = "radio";
      input.className = "barber-chip-input";
      input.name = "preferred_barber_id";
      input.id = "pref-" + id;
      input.value = id;
      input.dataset.barberId = id;

      const label = document.createElement("label");
      label.className = "barber-chip anim-enter";
      label.htmlFor = "pref-" + id;
      label.dataset.barberId = id;
      label.textContent = barber.name;

      group.appendChild(input);
      group.appendChild(label);

      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          label.classList.add("anim-enter-active");
        });
      });
    });

    if (selectedId && !nextIds.has(selectedId)) {
      const none = document.getElementById("pref-none");
      if (none) none.checked = true;
    }
  }
})();
