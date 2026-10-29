// Login and first-run setup pages: warns when this browser won't keep a login.
// Login cookies are marked Secure (HTTPS only) unless SESSION_COOKIE_SECURE is
// false, and a browser silently drops them on a plain http:// address, so
// logging in or creating the admin login looks like it did nothing. Rather than
// guess from the address, set a Secure test cookie the same way and see if it
// sticks: that's right behind an HTTPS proxy, on localhost (which some browsers
// allow and some don't), and when cookies are blocked altogether.
(function () {
  const warning = document.getElementById("cookie-warning");
  if (!warning) return;

  const name = "next_up_cookie_check";
  const secure = warning.dataset.secureCookies === "true";
  document.cookie = name + "=1; path=/; SameSite=Lax" + (secure ? "; Secure" : "");
  const kept = document.cookie.split("; ").indexOf(name + "=1") !== -1;
  document.cookie = name + "=; path=/; max-age=0" + (secure ? "; Secure" : "");
  if (kept) return;

  const reason = secure && window.location.protocol === "http:" ? "http" : "blocked";
  warning.querySelectorAll("[data-reason]").forEach(function (part) {
    part.hidden = part.dataset.reason !== reason;
  });
  warning.hidden = false;
})();
