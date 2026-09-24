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

  const initialTab = window.location.hash.replace("#", "");
  if (!initialTab || !activate(initialTab)) {
    activate(tabButtons[0].dataset.tab);
  }
})();
