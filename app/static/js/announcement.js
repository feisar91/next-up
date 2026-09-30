// Keeps the shop announcement on the TV and kiosk (#announcement, with its text
// in #announcement-text) in step with what staff set, without a reload. The
// kiosk's "You're checked in" screen has no announcement, so this does nothing there.
(function () {
  window.watchAnnouncement = function (socket) {
    const box = document.getElementById("announcement");
    const text = document.getElementById("announcement-text");

    socket.on("announcement", function (state) {
      if (!box || state.location !== window.LOCATION_SLUG) return;
      text.textContent = state.text || "";
      box.hidden = !state.text;
    });
  };
})();
