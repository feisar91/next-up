(function () {
  const tabButtons = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll("[data-tab-panel]");

  function activate(tabId) {
    let matched = false;
    panels.forEach(function (panel) {
      const isMatch = panel.dataset.tabPanel === tabId;
      panel.hidden = !isMatch;
      if (isMatch) matched = true;
    });
    tabButtons.forEach(function (btn) {
      const isMatch = btn.dataset.tab === tabId;
      btn.classList.toggle("active", isMatch);
      btn.setAttribute("aria-selected", isMatch ? "true" : "false");
    });
    return matched;
  }

  tabButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activate(btn.dataset.tab);
      history.replaceState(null, "", "#" + btn.dataset.tab);
    });
  });

  // A link to the page you're already on (plus a #tab) only scrolls, it never
  // reloads, so [data-reload] links reload explicitly. The URL, query string
  // (applied filters) and #tab all survive a reload.
  document.querySelectorAll("[data-reload]").forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      window.location.reload();
    });
  });

  const initialTab = window.location.hash.replace("#", "");
  if (!initialTab || !activate(initialTab)) {
    activate(tabButtons[0].dataset.tab);
  }
})();
