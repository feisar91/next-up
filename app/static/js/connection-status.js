// Shows the "Connection lost" banner (#connection-banner, from
// _connection_banner.html) on long-running screens while their live connection
// is down. A drop that reconnects within GRACE_MS shows nothing, so a Wi-Fi blip
// doesn't flash red at customers. onChange(lost) (optional) runs each time the
// banner shows or hides, e.g. for the kiosk to stop check-ins that would fail.
(function () {
  const GRACE_MS = 3000;

  window.watchConnection = function (socket, onChange) {
    const banner = document.getElementById("connection-banner");
    let timer = null;
    let lost = false;

    function setLost(value) {
      if (lost === value) return;
      lost = value;
      banner.hidden = !lost;
      if (onChange) onChange(lost);
    }

    function dropped() {
      if (lost || timer) return;
      timer = setTimeout(function () {
        timer = null;
        setLost(true);
      }, GRACE_MS);
    }

    socket.on("connect", function () {
      clearTimeout(timer);
      timer = null;
      setLost(false);
    });
    socket.on("disconnect", dropped);
    // A page that never connected (server down while it loaded from cache).
    socket.on("connect_error", dropped);
  };
})();
