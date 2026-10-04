// Keeps the kiosk and TV screens from dimming or locking (Screen Wake Lock API).
// The browser drops the lock whenever the page is hidden (screen off, tab
// switched, app in the background), so it's asked for again each time the page
// is visible. A request can also be refused, e.g. on low battery or before the
// page has had a tap, so the next tap tries again. Browsers without the API, or
// pages served over plain HTTP (it needs a secure context), just do nothing.
(function () {
  if (!("wakeLock" in navigator)) return;

  let lock = null;
  let requesting = false;

  function request() {
    if (lock || requesting || document.visibilityState !== "visible") return;
    requesting = true;
    navigator.wakeLock.request("screen").then(function (sentinel) {
      lock = sentinel;
      lock.addEventListener("release", function () {
        lock = null;
      });
    }).catch(function () {
      // Refused: try again on the next visibility change or tap.
    }).finally(function () {
      requesting = false;
    });
  }

  document.addEventListener("visibilitychange", request);
  document.addEventListener("pointerdown", request);
  request();
})();
