/* Ұйымдастырушы экраны: QR мен санауышты автоматты жаңартады. */
(function () {
  var root = document.getElementById("checkin");
  if (!root) return;
  var img = document.getElementById("checkin-qr");
  var fill = document.getElementById("checkin-bar-fill");
  var step = parseInt(root.dataset.step, 10) || 30;
  var started = Date.now();

  function refreshQr() {
    img.src = root.dataset.qr + "?t=" + Date.now();
    started = Date.now();
  }
  function refreshStats() {
    fetch(root.dataset.stats, { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        document.getElementById("checkin-attended").textContent = d.attended;
        document.getElementById("checkin-total").textContent = d.total;
      })
      .catch(function () {});
  }
  function tick() {
    var left = Math.max(0, 1 - (Date.now() - started) / (step * 1000));
    fill.style.width = (left * 100) + "%";
  }
  // QR әр қадамда (30 с) жаңарады; белгі ~90 с жарамды
  setInterval(refreshQr, step * 1000);
  setInterval(refreshStats, 4000);
  setInterval(tick, 250);
})();
