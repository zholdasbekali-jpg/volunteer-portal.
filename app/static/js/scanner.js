// QR-сканер: камера, сурет жүктеу. Декодтау браузерде (jsQR), тексеруді сервер жасайды:
// QR мазмұны /verify?code=... арқылы серверге жіберіледі, нөмірді сервер алып, тексереді.
(function () {
  "use strict";
  var root = document.getElementById("scanner");
  if (!root || typeof jsQR === "undefined") return;

  var target = root.dataset.url;
  var video = document.getElementById("scan-video");
  var startBtn = document.getElementById("scan-start");
  var stopBtn = document.getElementById("scan-stop");
  var fileInput = document.getElementById("scan-file");
  var msg = document.getElementById("scan-msg");
  var note = document.getElementById("scan-cam-note");
  var canvas = document.createElement("canvas");
  var ctx = canvas.getContext("2d", { willReadFrequently: true });
  var stream = null, timer = null;

  function say(text) { msg.textContent = text; msg.hidden = !text; }
  function go(text) { window.location.href = target + "?code=" + encodeURIComponent(String(text).slice(0, 300)); }

  // Кадрды/суретті canvas-қа салып, QR іздейді (үлкен суреттерді кішірейтеміз)
  function decode(source, w, h, limit) {
    var scale = Math.min(1, (limit || 900) / Math.max(w, h));
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
    var img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    return jsQR(img.data, img.width, img.height, { inversionAttempts: "attemptBoth" });
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    video.hidden = true; stopBtn.hidden = true; startBtn.hidden = false;
  }

  function tick() {
    if (!video.videoWidth || video.readyState < 2) return;
    var result = decode(video, video.videoWidth, video.videoHeight, 1280);
    if (result && result.data) { stop(); go(result.data); }
  }

  var cameraOk = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  if (!cameraOk) { startBtn.hidden = true; note.hidden = false; }

  startBtn.addEventListener("click", function () {
    say("");
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
      .then(function (s) {
        stream = s; video.srcObject = s; video.hidden = false;
        startBtn.hidden = true; stopBtn.hidden = false;
        video.play();
        timer = setInterval(tick, 200);
      })
      .catch(function () {
        say("Камераға рұқсат берілмеді немесе камера табылмады. Фотоны жүктеңіз немесе нөмірді қолмен енгізіңіз.");
      });
  });
  stopBtn.addEventListener("click", stop);

  fileInput.addEventListener("change", function () {
    var file = fileInput.files && fileInput.files[0];
    if (!file) return;
    say("");
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var result = decode(img, img.naturalWidth, img.naturalHeight, 1600);
      URL.revokeObjectURL(url);
      if (result && result.data) go(result.data);
      else say("Суреттен QR-код табылмады. Анығырақ, жақынырақ түсіріп көріңіз немесе нөмірді қолмен енгізіңіз.");
    };
    img.onerror = function () { URL.revokeObjectURL(url); say("Суретті оқу мүмкін болмады."); };
    img.src = url;
  });

  window.addEventListener("pagehide", stop);
})();
