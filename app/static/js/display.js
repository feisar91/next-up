(function () {
  const socket = io({ path: "/updates" });
  const chairList = document.getElementById("chair-list");
  const waitingList = document.getElementById("waiting-list");
  const chairEmpty = document.getElementById("chair-empty");
  const waitingEmpty = document.getElementById("waiting-empty");
  const connectionBanner = document.getElementById("connection-banner");

  socket.on("connect", function () {
    connectionBanner.hidden = true;
    socket.emit("join", { location: window.LOCATION_SLUG, token: window.DISPLAY_TOKEN });
  });

  socket.on("disconnect", function () {
    connectionBanner.hidden = false;
  });

  socket.on("queue_update", function (state) {
    if (state.location !== window.LOCATION_SLUG) return;
    renderChair(state.in_progress);
    renderWaiting(state.waiting);
  });

  function renderChair(entries) {
    chairEmpty.hidden = entries.length > 0;

    AnimatedList.render(
      chairList,
      entries,
      function (entry) {
        return entry.id;
      },
      function (entry) {
        const li = document.createElement("li");
        li.className = "chair-card";
        li.innerHTML = '<span class="customer-name"></span><span class="barber-name"></span>';
        updateChairCard(li, entry);
        return li;
      },
      updateChairCard
    );
  }

  function updateChairCard(li, entry) {
    li.querySelector(".customer-name").textContent = entry.customer_name;
    li.querySelector(".barber-name").textContent = entry.called_by || "";
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
        const li = document.createElement("li");
        li.className = "waiting-row";
        li.innerHTML =
          '<span class="queue-number"></span><span class="customer-name"></span><span class="preferred-barber"></span>';
        updateWaitingRow(li, entry, index);
        return li;
      },
      updateWaitingRow
    );
  }

  function updateWaitingRow(li, entry, index) {
    li.querySelector(".queue-number").textContent = "#" + (index + 1);
    li.querySelector(".customer-name").textContent = entry.customer_name;
    li.querySelector(".preferred-barber").textContent = entry.preferred_barber
      ? "Prefers " + entry.preferred_barber
      : "";
  }
})();
