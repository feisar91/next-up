(function () {
  const RED = "#ea1f27";
  const RED_DARK = "#c8181f";
  const GRID = "#c2c3c1";
  const INK = "#282721";

  Chart.defaults.font.family = "'Inter Tight', 'Inter', system-ui, sans-serif";
  Chart.defaults.color = INK;

  function barChart(canvasId, labels, data, formatLabel, extra) {
    const el = document.getElementById(canvasId);
    if (!el) return;
    extra = extra || {};
    const horizontal = !!extra.horizontal;
    const valueAxis = {
      beginAtZero: true,
      ticks: { precision: 0, color: INK },
      grid: { color: GRID, drawTicks: false },
      border: { display: false },
    };
    const categoryAxis = {
      grid: { display: false },
      ticks: { color: INK },
    };

    new Chart(el, {
      type: "bar",
      data: {
        labels: labels.map(formatLabel || (function (l) { return l; })),
        datasets: [
          {
            data: data,
            backgroundColor: RED,
            hoverBackgroundColor: RED_DARK,
            borderRadius: horizontal
              ? { topLeft: 0, bottomLeft: 0, topRight: 4, bottomRight: 4 }
              : { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 },
            borderSkipped: horizontal ? "left" : "bottom",
            maxBarThickness: 24,
            categoryPercentage: 0.7,
          },
        ],
      },
      options: {
        indexAxis: horizontal ? "y" : "x",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: INK,
            padding: 10,
            cornerRadius: 6,
            displayColors: false,
            titleFont: { family: "'Oswald', sans-serif", size: 13 },
            bodyFont: { size: 13 },
            callbacks: extra.tooltipLabel ? { label: extra.tooltipLabel } : {},
          },
        },
        scales: horizontal
          ? { x: valueAxis, y: categoryAxis }
          : { x: categoryAxis, y: valueAxis },
      },
    });
  }

  function formatDay(iso) {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  const m = window.METRICS || {};
  barChart("cuts-by-day-chart", m.dayLabels || [], m.cutsSeries || [], formatDay);
  barChart("cuts-by-barber-chart", m.barberLabels || [], m.barberSeries || []);
  barChart("cuts-by-location-chart", m.locationLabels || [], m.locationSeries || []);

  const serviceRows = m.serviceRows || [];
  barChart(
    "service-by-barber-chart",
    serviceRows.map(function (r) { return r.barber; }),
    serviceRows.map(function (r) { return r.avg_minutes; }),
    null,
    {
      horizontal: true,
      tooltipLabel: function (ctx) {
        const row = serviceRows[ctx.dataIndex];
        return row.avg_minutes + " min average - " + row.cuts + (row.cuts === 1 ? " cut" : " cuts");
      },
    }
  );

  // --- Busiest-times heatmap: location picker + cell tooltip ---
  const picker = document.getElementById("heatmap-view");
  if (picker) {
    picker.addEventListener("change", function () {
      document.querySelectorAll("[data-heatmap-view]").forEach(function (view) {
        view.hidden = view.dataset.heatmapView !== picker.value;
      });
    });
  }

  const tooltip = document.querySelector(".heatmap-tooltip");
  if (tooltip) {
    function show(cell) {
      tooltip.innerHTML = "";
      const title = document.createElement("strong");
      title.textContent = cell.dataset.tipTitle;
      tooltip.appendChild(title);
      tooltip.appendChild(document.createTextNode(cell.dataset.tipBody));
      tooltip.hidden = false;

      const rect = cell.getBoundingClientRect();
      const tipRect = tooltip.getBoundingClientRect();
      let left = rect.left + rect.width / 2 - tipRect.width / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
      let top = rect.top - tipRect.height - 8;
      if (top < 8) top = rect.bottom + 8;
      tooltip.style.left = left + "px";
      tooltip.style.top = top + "px";
    }
    function hide() {
      tooltip.hidden = true;
    }

    document.querySelectorAll(".heatmap td").forEach(function (cell) {
      cell.addEventListener("mouseenter", function () { show(cell); });
      cell.addEventListener("mouseleave", hide);
      cell.addEventListener("focus", function () { show(cell); });
      cell.addEventListener("blur", hide);
    });
    window.addEventListener("scroll", hide, { passive: true });
  }
})();
