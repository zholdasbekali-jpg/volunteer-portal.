// Клиенттік көмекшілер. Негізгі тексеру — серверде; бұл тек ыңғайлылық үшін.
(function () {
  "use strict";

  // Қауіпті әрекеттерді растау: <form data-confirm="Хабарлама">
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // Қайталап жіберуден қорғау + жүктелу күйі
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      if (!form.checkValidity()) return;
      var btn = form.querySelector("button[type=submit][data-loading]");
      if (btn) {
        btn.disabled = true;
        btn.dataset.orig = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>' + btn.dataset.loading;
      }
    });
  });

  // Bootstrap-тың клиенттік валидациясы
  document.querySelectorAll("form.needs-validation").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!form.checkValidity()) { e.preventDefault(); e.stopPropagation(); }
      form.classList.add("was-validated");
    });
  });

  // Графиктердің жүктелу/қате күйі
  document.querySelectorAll(".chart-box img").forEach(function (img) {
    var box = img.closest(".chart-box");
    if (!img.complete) box.classList.add("loading");
    img.addEventListener("load", function () { box.classList.remove("loading"); });
    img.addEventListener("error", function () {
      box.classList.remove("loading");
      box.innerHTML = '<div class="empty"><i class="bi bi-exclamation-triangle"></i>График жүктелмеді. Бетті жаңартып көріңіз.</div>';
    });
  });

  // Хабарламаларды біраз уақыттан кейін жасыру (қателер қалады)
  document.querySelectorAll(".alert-success, .alert-info").forEach(function (el) {
    setTimeout(function () {
      if (window.bootstrap) bootstrap.Alert.getOrCreateInstance(el).close();
    }, 6000);
  });
})();
