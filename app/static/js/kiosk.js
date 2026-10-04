// Keeps the "preferred barber" chip list in sync with who's actually on duty,
// so a barber logging in at this location shows up here without a page reload.
(function () {
  const socket = io({ path: "/updates" });
  // Only present on the check-in form, not on the "we're closed" screen - but
  // the socket still needs to connect and listen there too, for store_status
  // to bring the form back without a manual refresh.
  const group = document.getElementById("barber-chip-group");

  // Don't reload for an update while a customer is partway through checking in.
  function customerIsTyping() {
    return Array.from(document.querySelectorAll('.kiosk-form input[name="customer_name"]')).some(function (name) {
      return name.value.trim();
    });
  }

  // "Add another person": a parent checking in their kids too. Each extra row
  // is another customer_name, and the server gives them consecutive places.
  const groupPeople = document.getElementById("group-people");
  const addPerson = document.getElementById("add-person");
  const personTemplate = document.getElementById("group-person-template");

  function updateAddPerson() {
    const maxGroupSize = Number(addPerson.dataset.maxGroupSize);
    addPerson.hidden = groupPeople.children.length + 1 >= maxGroupSize;
  }

  function removeExtraPeople() {
    if (!groupPeople) return;
    groupPeople.replaceChildren();
    updateAddPerson();
  }

  if (addPerson) {
    addPerson.addEventListener("click", function () {
      const row = personTemplate.content.firstElementChild.cloneNode(true);
      groupPeople.appendChild(row);
      row.querySelector("input").focus();
      updateAddPerson();
    });
    groupPeople.addEventListener("click", function (e) {
      const remove = e.target.closest(".remove-person");
      if (!remove) return;
      remove.closest(".group-person").remove();
      updateAddPerson();
    });
  }

  // Someone who types a name and walks off shouldn't leave it for the next
  // customer to see, or hold off reloads indefinitely: after a minute with no
  // typing or tapping, clear the form (the deploy reload retries by itself).
  const IDLE_CLEAR_MS = 60000;
  const form = document.querySelector(".kiosk-form");
  let idleTimer = null;
  let skippedStoreClosed = null; // open/closed state a skipped store_status reload was for

  function clearAbandonedForm() {
    form.reset(); // empty name, "No preference" selected
    removeExtraPeople();
    if (skippedStoreClosed !== null && skippedStoreClosed !== window.STORE_CLOSED) {
      window.location.reload();
    }
  }

  if (form) {
    ["input", "change", "pointerdown", "keydown"].forEach(function (eventName) {
      form.addEventListener(eventName, function () {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(clearAbandonedForm, IDLE_CLEAR_MS);
      });
    });
  }

  // A check-in sent while the server can't be reached would leave the tablet on
  // the browser's error page, so hold the button until the connection is back.
  // (A button already showing its loading state is mid-submit: leave it alone.)
  window.watchConnection(socket, function (lost) {
    const button = form && form.querySelector("button[type=submit]");
    if (button && !button.classList.contains("is-loading")) button.disabled = lost;
  });

  // Swapping the announcement text doesn't disturb a customer partway through
  // typing, so unlike the store_status reload below it never waits.
  window.watchAnnouncement(socket);

  socket.on("connect", function () {
    socket.emit("join", { location: window.LOCATION_SLUG, token: window.KIOSK_TOKEN }, function (ack) {
      window.checkAppVersion(ack, customerIsTyping);
    });
  });

  socket.on("barbers_update", function (state) {
    if (!group) return;
    if (state.location !== window.LOCATION_SLUG) return;
    renderBarbers(state.barbers);
  });

  // Open/closed changes the whole screen (form vs. "we're closed"), which isn't
  // worth re-rendering client-side - reload, same as an app version change,
  // unless a customer is partway through checking in (then it waits for them to
  // submit, or for clearAbandonedForm).
  socket.on("store_status", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    skippedStoreClosed = null;
    if (state.closed === window.STORE_CLOSED) return;
    if (customerIsTyping()) {
      skippedStoreClosed = state.closed;
      return;
    }
    window.location.reload();
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
