// The public demo's banner (_demo_banner.html): counts down to the next reset.
// Ordinary pages reload a few seconds after it, since the reset logs everyone
// out; the kiosk and TV are told to reload by the server instead.
(function () {
  const banner = document.currentScript.previousElementSibling;
  const countdown = banner && banner.querySelector("[data-demo-countdown]");
  if (!countdown) return;

  const intervalMs = Number(banner.dataset.intervalMinutes) * 60000;
  const reloadOnReset = banner.hasAttribute("data-reload-on-reset");
  let resetAt = Date.parse(banner.dataset.resetsAt);
  if (!intervalMs || isNaN(resetAt)) return;

  function update() {
    const now = Date.now();
    if (now >= resetAt) {
      if (reloadOnReset) {
        countdown.textContent = "now";
        setTimeout(function () { window.location.reload(); }, 5000);
        return;
      }
      while (resetAt <= now) resetAt += intervalMs;
    }
    const minutes = Math.ceil((resetAt - now) / 60000);
    countdown.textContent = minutes <= 1 ? "in under a minute" : "in " + minutes + " minutes";
    setTimeout(update, 15000);
  }
  update();
})();
