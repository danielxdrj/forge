(function () {
  "use strict";

  var STORAGE_KEY = "forge-theme";

  function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function readStored() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      if (value === "light" || value === "dark") {
        return value;
      }
    } catch (err) {
      return null;
    }
    return null;
  }

  function currentTheme() {
    return readStored() || systemTheme();
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var button = document.getElementById("theme-toggle");
    if (!button) {
      return;
    }
    var isDark = theme === "dark";
    button.setAttribute("aria-pressed", isDark ? "true" : "false");
    button.setAttribute("aria-label", isDark ? "Ativar modo claro" : "Ativar modo escuro");
    var label = button.querySelector(".theme-toggle-text");
    if (label) {
      label.textContent = isDark ? "Modo claro" : "Modo escuro";
    }
  }

  applyTheme(currentTheme());

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(currentTheme());
    var button = document.getElementById("theme-toggle");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch (err) {
        /* ignore quota / private mode */
      }
      applyTheme(next);
    });
  });
})();
