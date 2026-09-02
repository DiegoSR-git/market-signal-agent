(() => {
  const status = document.querySelector("[data-alpha-status]");
  if (!status) return;
  fetch("./snapshot.json", { cache: "no-store" })
    .then((response) => response.ok ? response.json() : null)
    .then((snapshot) => {
      if (!snapshot) return;
      status.textContent = `${snapshot.market_status || "UNKNOWN"} · ${snapshot.analysis_timestamp || ""}`;
    })
    .catch(() => {
      status.textContent = "Snapshot no disponible";
    });
})();
