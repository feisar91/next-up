// Keeps the admin Device Links tab's "Online" / "Offline since ..." lines live.
// The server sends each location's lines already rendered (the same macro as the
// page, _device_status.html), so this only swaps them in. A screen that just
// dropped off comes with offline_in: the server sends nothing when that grace
// runs out, so this asks again then.
(function () {
  const socket = io({ path: "/updates" });
  const graceTimers = {};

  function refresh() {
    socket.emit("watch_devices", function (updates) {
      (updates || []).forEach(apply);
    });
  }

  function apply(update) {
    ["kiosk", "display"].forEach(function (kind) {
      const slot = document.getElementById("device-status-" + update.location_id + "-" + kind);
      if (!slot) return; // a location added or restored since the page loaded
      slot.innerHTML = update[kind].html;

      const key = update.location_id + "-" + kind;
      clearTimeout(graceTimers[key]);
      if (update[kind].offline_in !== null) {
        // A second late, so the server agrees the grace is over.
        graceTimers[key] = setTimeout(refresh, (update[kind].offline_in + 1) * 1000);
      }
    });
  }

  // On every connect, including reconnects: changes may have been missed meanwhile.
  socket.on("connect", refresh);
  socket.on("device_status", apply);
})();
