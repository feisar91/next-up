(function () {
  const socket = io({ path: "/updates" });
  const chairList = document.getElementById("chair-list");
  const waitingList = document.getElementById("waiting-list");
  const chairEmpty = document.getElementById("chair-empty");
  const waitingEmpty = document.getElementById("waiting-empty");
  const recentCard = document.getElementById("recent-card");
  const recentList = document.getElementById("recent-list");
  // Recently finished entries, each with expiresAt (this device's clock) for when
  // Undo stops being offered. The server sends seconds remaining rather than a
  // time, so a tablet with a wrong clock still hides rows on time.
  let recent = [];

  window.watchConnection(socket);

  socket.on("connect", function () {
    socket.emit("join", { location: window.LOCATION_SLUG }, function (ack) {
      window.checkAppVersion(ack);
    });
  });
  socket.on("app_version", function (ack) {
    window.checkAppVersion(ack);
  });

  socket.on("queue_update", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    renderChair(state.in_progress);
    renderWaiting(state.waiting);
    setRecent(state.recent || []);
  });

  // "The kiosk isn't connected" on the store card (only there while the store is
  // open). A kiosk that just dropped off gets offline_in seconds to come back
  // before the note shows; if it reconnects first, a new status cancels that.
  const kioskOfflineNote = document.getElementById("kiosk-offline-note");
  let kioskOfflineTimer = null;

  socket.on("kiosk_status", function (state) {
    if (!kioskOfflineNote || state.location !== window.LOCATION_SLUG) return;
    clearTimeout(kioskOfflineTimer);
    kioskOfflineNote.hidden = !state.offline;
    if (state.offline_in !== null) {
      kioskOfflineTimer = setTimeout(function () {
        kioskOfflineNote.hidden = false;
      }, state.offline_in * 1000);
    }
  });

  // Another barber (or an admin) changed the announcement: show it, unless this
  // barber is busy typing their own.
  const announcementInput = document.getElementById("announcement");
  const announcementClear = document.getElementById("announcement-clear-button");

  socket.on("announcement", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    if (document.activeElement !== announcementInput) announcementInput.value = state.text || "";
    announcementClear.hidden = !state.text;
  });

  // The store can open or close on its opening hours with nobody tapping the
  // button, so reload to show the new state (a page load re-renders the card).
  socket.on("store_status", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    if (state.closed === window.STORE_CLOSED) return;
    window.location.reload();
  });

  setRecent(window.INITIAL_RECENT || []);
  setInterval(renderRecent, 5000);

  function actionForm(action, label, className, confirmText) {
    const form = document.createElement("form");
    form.method = "post";
    form.action = action;

    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrf_token";
    csrf.value = document.querySelector('meta[name="csrf-token"]').content;
    form.appendChild(csrf);
    if (confirmText) form.dataset.confirm = confirmText;

    const btn = document.createElement("button");
    btn.type = "submit";
    btn.className = className;
    btn.textContent = label;
    form.appendChild(btn);
    return form;
  }

  function renderChair(entries) {
    chairEmpty.hidden = entries.length > 0;

    AnimatedList.render(
      chairList,
      entries,
      function (entry) {
        return entry.id;
      },
      function (entry) {
        const row = document.createElement("div");
        row.className = "staff-row";

        const info = document.createElement("div");
        const strong = document.createElement("strong");
        const meta = document.createElement("div");
        meta.className = "meta";
        info.appendChild(strong);
        info.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "staff-actions";
        actions.appendChild(actionForm(window.URLS.complete + entry.id, "Complete", "btn"));

        row.appendChild(info);
        row.appendChild(actions);
        updateChairRow(row, entry);
        return row;
      },
      updateChairRow
    );
  }

  function updateChairRow(row, entry) {
    row.querySelector("strong").textContent = entry.customer_name;
    row.querySelector(".meta").textContent = "with " + (entry.called_by || "");
  }

  function renderWaiting(entries) {
    waitingEmpty.hidden = entries.length > 0;

    AnimatedList.render(
      waitingList,
      entries,
      function (entry) {
        return entry.id;
      },
      function (entry, index) {
        const row = document.createElement("div");
        row.className = "staff-row";

        const info = document.createElement("div");
        const number = document.createElement("span");
        number.className = "queue-number";
        const strong = document.createElement("strong");
        const meta = document.createElement("div");
        meta.className = "meta";
        info.appendChild(number);
        info.appendChild(document.createTextNode(" "));
        info.appendChild(strong);
        info.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "staff-actions";
        actions.appendChild(actionForm(window.URLS.call + entry.id, "Call to Chair", "btn"));
        actions.appendChild(
          actionForm(
            window.URLS.remove + entry.id,
            "Remove",
            "btn btn-danger",
            "Remove " + entry.customer_name + " from the queue?"
          )
        );

        row.appendChild(info);
        row.appendChild(actions);
        updateWaitingRow(row, entry, index);
        return row;
      },
      updateWaitingRow
    );
  }

  function setRecent(entries) {
    const now = Date.now();
    recent = entries.map(function (entry) {
      return Object.assign({}, entry, { expiresAt: now + entry.undo_seconds * 1000 });
    });
    renderRecent();
  }

  function renderRecent() {
    const now = Date.now();
    const entries = recent.filter(function (entry) {
      return entry.expiresAt > now;
    });
    recentCard.hidden = entries.length === 0;

    AnimatedList.render(
      recentList,
      entries,
      function (entry) {
        return entry.id;
      },
      function (entry) {
        const row = document.createElement("div");
        row.className = "staff-row";

        const info = document.createElement("div");
        const strong = document.createElement("strong");
        const meta = document.createElement("div");
        meta.className = "meta";
        info.appendChild(strong);
        info.appendChild(meta);

        const actions = document.createElement("div");
        actions.className = "staff-actions";
        actions.appendChild(actionForm(window.URLS.undo + entry.id, "Undo", "btn btn-secondary"));

        row.appendChild(info);
        row.appendChild(actions);
        updateRecentRow(row, entry);
        return row;
      },
      updateRecentRow
    );
  }

  function updateRecentRow(row, entry) {
    row.querySelector("strong").textContent = entry.customer_name;
    row.querySelector(".meta").textContent =
      entry.status === "done" ? "Completed with " + (entry.called_by || "") : "Removed from the queue";
  }

  function updateWaitingRow(row, entry, index) {
    row.querySelector(".queue-number").textContent = "#" + (index + 1);
    row.querySelector("strong").textContent = entry.customer_name;
    const meta = row.querySelector(".meta");
    // Customers who asked for the barber viewing this page stand out.
    const mine = entry.preferred_barber_id === window.CURRENT_BARBER_ID;
    row.classList.toggle("is-mine", mine);
    if (entry.preferred_barber) {
      meta.textContent = mine ? "Asked for you" : "Prefers " + entry.preferred_barber;
      meta.hidden = false;
    } else {
      meta.hidden = true;
    }
  }
})();
