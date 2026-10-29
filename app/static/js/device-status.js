// Keeps the admin Device Links tab's "Online" / "Offline since ..." lines live.
// The server sends each location's lines already rendered (the same macro as the
// page, _device_status.html), so this only swaps them in. A screen that just
// dropped off comes with offline_in: the server sends nothing when that grace
// runs out, so this asks again then.
//
// It also ticks the Getting Started checklist's "open the links" step as soon as
// a kiosk and a TV have each connected, without a page reload.
(function () {
  const socket = io({ path: "/updates" });
  const graceTimers = {};
  const devicesStep = document.querySelector('[data-step="devices"]');

  function showDevicesStep() {
    if (!devicesStep) return;
    const kiosk = devicesStep.dataset.kioskSeen === "true";
    const display = devicesStep.dataset.displaySeen === "true";
    const done = kiosk && display;
    let text = "";
    if (!done) {
      if (kiosk) text = "Kiosk connected. Waiting for the TV.";
      else if (display) text = "TV connected. Waiting for the kiosk.";
      else text = "Waiting for the kiosk and the TV to connect.";
    }
    devicesStep.querySelector(".setup-step-status").textContent = text;
    devicesStep.classList.toggle("is-done", done);
    devicesStep.querySelector(".step-done-label").hidden = !done;

    const steps = document.querySelectorAll("#setup-steps li");
    const allDone = Array.prototype.every.call(steps, function (li) {
      return li.classList.contains("is-done");
    });
    document.getElementById("setup-all-done").hidden = !allDone;
  }

  function noteSeen(update) {
    if (!devicesStep) return;
    if (update.kiosk.state !== "never") devicesStep.dataset.kioskSeen = "true";
    if (update.display.state !== "never") devicesStep.dataset.displaySeen = "true";
    showDevicesStep();
  }

  function refresh() {
    socket.emit("watch_devices", function (updates) {
      (updates || []).forEach(apply);
    });
  }

  function apply(update) {
    noteSeen(update);
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

  showDevicesStep();

  // On every connect, including reconnects: changes may have been missed meanwhile.
  socket.on("connect", refresh);
  socket.on("device_status", apply);
})();
