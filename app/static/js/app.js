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
      box.innerHTML = '<div class="empty"><i class="bi bi-exclamation-triangle"></i></div>';
      box.firstChild.appendChild(document.createTextNode(document.body.dataset.chartError || ""));
    });
  });

  // Хабарламаларды біраз уақыттан кейін жасыру (қателер қалады)
  document.querySelectorAll(".alert-success, .alert-info").forEach(function (el) {
    setTimeout(function () {
      if (window.bootstrap) bootstrap.Alert.getOrCreateInstance(el).close();
    }, 6000);
  });

  // Басқару беттеріндегі бөлімдер: сілтеме (%23users т.с.с.) арқылы ашылады
  var tabs = document.querySelectorAll('[data-bs-toggle="pill"], [data-bs-toggle="tab"]');
  if (window.bootstrap && tabs.length) {
    var hash = window.location.hash.replace("#", "");
    if (hash) {
      Array.prototype.forEach.call(tabs, function (tab) {
        if (tab.getAttribute("data-bs-target") === "#" + hash) {
          bootstrap.Tab.getOrCreateInstance(tab).show();
        }
      });
    }
    Array.prototype.forEach.call(tabs, function (tab) {
      tab.addEventListener("shown.bs.tab", function () {
        var target = tab.getAttribute("data-bs-target");
        if (window.history.replaceState) window.history.replaceState(null, "", target);
        else window.location.hash = target;
      });
    });
  }

  // Қатысушылар кестесіндегі жаппай таңдау мен «Қолдану» түймесі.
  // Чекбокстар кестеде, ал форма оның сыртында: form="..." атрибуты арқылы байланысады.
  document.querySelectorAll("[data-select-all]").forEach(function (master) {
    var formId = master.dataset.selectAll;
    var form = document.getElementById(formId);
    if (!form) return;
    var boxes = document.querySelectorAll('input[type="checkbox"][name="ids"][form="' + formId + '"]');
    var apply = form.querySelector("[data-bulk-apply]");
    var sync = function () {
      if (apply) {
        apply.disabled = !Array.prototype.some.call(boxes, function (box) { return box.checked; });
      }
    };
    master.addEventListener("change", function () {
      Array.prototype.forEach.call(boxes, function (box) { box.checked = master.checked; });
      sync();
    });
    Array.prototype.forEach.call(boxes, function (box) { box.addEventListener("change", sync); });
    sync();
  });
})();
