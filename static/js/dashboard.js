// Dashboard: draw the rate chart and reload the page when a filter changes.
(function () {
  const form = document.getElementById("chart-form");
  if (form) {
    form.addEventListener("change", () => form.submit());
  }

  const dataEl = document.getElementById("chart-data");
  const canvas = document.getElementById("rate-chart");
  if (!dataEl || !canvas || typeof Chart === "undefined") return;

  const data = JSON.parse(dataEl.textContent);
  const styles = getComputedStyle(document.documentElement);
  const accent = styles.getPropertyValue("--accent").trim();
  const muted = styles.getPropertyValue("--muted").trim();
  const grid = styles.getPropertyValue("--border").trim();

  new Chart(canvas, {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [{
        label: `${data.code} / UAH`,
        data: data.values,
        borderColor: accent,
        backgroundColor: accent + "22",
        fill: true,
        tension: 0.2,
        pointRadius: 0,
        pointHoverRadius: 4,
        borderWidth: 2,
      }],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (ctx) => ` ${ctx.parsed.y.toFixed(4)} ₴` },
        },
      },
      scales: {
        x: {
          ticks: { color: muted, maxTicksLimit: 8, maxRotation: 0 },
          grid: { display: false },
        },
        y: {
          ticks: { color: muted },
          grid: { color: grid },
        },
      },
    },
  });
})();
