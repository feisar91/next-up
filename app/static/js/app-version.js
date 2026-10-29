// Reloads long-running screens (kiosk, TV display, staff dashboard) after a
// deploy or a branding change. Each screen passes checkAppVersion as the ack
// callback of its socket "join" (sent on every connect and reconnect), and also
// calls it on the "app_version" event the server sends when the branding
// changes. If the version isn't the one this page was built with, the page
// reloads to pick up the new code or look.
(function () {
  const RETRY_MS = 15000;
  const MIN_GAP_MS = 60000; // never reload more than once a minute, whatever happens
  let pending = false;

  // Milliseconds until another reload is allowed (0 if it is now).
  function waitBeforeReload() {
    try {
      const last = Number(sessionStorage.getItem("appVersionReloadAt") || 0);
      return Math.max(0, last + MIN_GAP_MS - Date.now());
    } catch (e) {
      return 0;
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
    pending = true;
    // Just reloaded (e.g. two branding changes in a row): wait out the gap, then
    // reload once more so the screen still ends up current.
    setTimeout(function () { reloadWhenIdle(isBusy); }, waitBeforeReload());
  };
})();
