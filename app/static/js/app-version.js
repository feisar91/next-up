// Reloads long-running screens (kiosk, TV display, staff dashboard) after a
// deploy. Each screen passes checkAppVersion as the ack callback of its socket
// "join" (sent on every connect and reconnect); the server answers with its
// current version, and if that isn't the version this page was built with, the
// page reloads to pick up the new code.
(function () {
  const RETRY_MS = 15000;
  const MIN_GAP_MS = 60000; // never reload more than once a minute, whatever happens
  let pending = false;

  function recentlyReloaded() {
    try {
      const last = Number(sessionStorage.getItem("appVersionReloadAt") || 0);
      return Date.now() - last < MIN_GAP_MS;
    } catch (e) {
      return false;
    }
  }

  function reloadWhenIdle(isBusy) {
    if (isBusy && isBusy()) {
      setTimeout(function () { reloadWhenIdle(isBusy); }, RETRY_MS);
      return;
    }
    try {
      sessionStorage.setItem("appVersionReloadAt", String(Date.now()));
    } catch (e) {
      // Storage unavailable: reload anyway.
    }
    window.location.reload();
  }

  // isBusy (optional): returns true while reloading would lose something, e.g. a
  // customer halfway through typing their name. The reload waits until it's false.
  window.checkAppVersion = function (ack, isBusy) {
    if (pending || !ack || !ack.version || ack.version === window.APP_VERSION) return;
    if (recentlyReloaded()) return;
    pending = true;
    reloadWhenIdle(isBusy);
  };
})();
