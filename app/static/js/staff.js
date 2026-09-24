(function () {
  const socket = io({ path: "/updates" });
  const chairList = document.getElementById("chair-list");
  const waitingList = document.getElementById("waiting-list");
  const chairEmpty = document.getElementById("chair-empty");
  const waitingEmpty = document.getElementById("waiting-empty");

  socket.on("connect", function () {
    socket.emit("join", { location: window.LOCATION_SLUG });
  });

  socket.on("queue_update", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    renderChair(state.in_progress);
    renderWaiting(state.waiting);
  });

  function actionForm(action, label, className, confirmText) {
    const form = document.createElement("form");
    form.method = "post";
    form.action = action;
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

  function updateWaitingRow(row, entry, index) {
    row.querySelector(".queue-number").textContent = "#" + (index + 1);
    row.querySelector("strong").textContent = entry.customer_name;
    const meta = row.querySelector(".meta");
    if (entry.preferred_barber) {
      meta.textContent = "Prefers " + entry.preferred_barber;
      meta.hidden = false;
    } else {
      meta.hidden = true;
    }
  }
})();
