(function () {
  var glossary = window.PLAYBOOK_GLOSSARY || {};

  function closest(el, selector) {
    return el && el.closest ? el.closest(selector) : null;
  }

  function ensurePopover() {
    var pop = document.getElementById("term-popover");
    if (pop) return pop;
    pop = document.createElement("div");
    pop.className = "term-popover";
    pop.id = "term-popover";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-modal", "false");
    pop.setAttribute("aria-labelledby", "pop-title");
    pop.setAttribute("aria-live", "polite");
    pop.innerHTML = '<button class="pop-close" type="button" aria-label="Close definition">&times;</button><div class="pop-title" id="pop-title"></div><p class="pop-def" id="pop-def"></p>';
    document.body.appendChild(pop);
    return pop;
  }

  function initGlossary() {
    var pop = ensurePopover();
    var popTitle = pop.querySelector(".pop-title");
    var popDef = pop.querySelector(".pop-def");
    var popClose = pop.querySelector(".pop-close");
    var lastTermEl = null;

    function openPop(termEl) {
      var entry = glossary[termEl.dataset.def];
      if (!entry) return;
      popTitle.textContent = entry.title;
      popDef.textContent = entry.def;
      pop.classList.add("open");

      var rect = termEl.getBoundingClientRect();
      var popWidth = Math.min(340, window.innerWidth - 32);
      pop.style.maxWidth = popWidth + "px";
      var left = rect.left + window.scrollX;
      if (left + popWidth > window.scrollX + window.innerWidth - 16) {
        left = window.scrollX + window.innerWidth - popWidth - 16;
      }
      if (left < window.scrollX + 16) left = window.scrollX + 16;
      pop.style.left = left + "px";
      pop.style.top = rect.bottom + window.scrollY + 6 + "px";
      lastTermEl = termEl;
    }

    function closePop() {
      pop.classList.remove("open");
      if (lastTermEl) {
        try { lastTermEl.focus(); } catch (e) {}
      }
      lastTermEl = null;
    }

    document.addEventListener("click", function (e) {
      var termEl = closest(e.target, "button.term");
      if (termEl) {
        e.preventDefault();
        openPop(termEl);
        return;
      }
      if (!closest(e.target, ".term-popover")) closePop();
    });

    if (popClose) {
      popClose.addEventListener("click", function (e) {
        e.stopPropagation();
        closePop();
      });
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.keyCode === 27) closePop();
    });

    window.addEventListener("resize", function () {
      if (pop.classList.contains("open") && lastTermEl) openPop(lastTermEl);
    });
  }

  function initSectionNav() {
    document.querySelectorAll("[data-scroll-target]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.querySelector(button.dataset.scrollTarget);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function initPhraseTool() {
    document.querySelectorAll(".phrase-tool").forEach(function (tool) {
      var cards = Array.prototype.slice.call(tool.querySelectorAll(".phrase-card"));
      var buttons = Array.prototype.slice.call(tool.querySelectorAll("[data-filter-stage]"));
      var status = tool.querySelector("[data-copy-status]");
      var routeSelect = tool.querySelector("[data-route-select]");
      var routeOutput = tool.querySelector("[data-route-output]");
      var routes = {
        next: "Type: What's next?",
        feature: "Type: I want to build [feature].",
        fuzzy: "Type: Before we code, make a mockup.",
        sliced: "Type: Build slice 1.",
        continue: "Type: Build the next slice.",
        correction: "Type your correction plainly, for example: This label is wrong.",
        mobile: "Type: Check this on mobile too.",
        ship: "Type: Ship the feature.",
        merged: "Type: I reviewed and merged the PR. Can you check?"
      };

      function setFilter(stage) {
        buttons.forEach(function (button) {
          var active = button.dataset.filterStage === stage;
          button.classList.toggle("active", active);
          button.setAttribute("aria-pressed", active ? "true" : "false");
        });
        cards.forEach(function (card) {
          var show = stage === "all" || card.dataset.stage === stage;
          card.hidden = !show;
        });
      }

      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          setFilter(button.dataset.filterStage);
        });
      });
      setFilter("all");

      tool.addEventListener("click", function (e) {
        var copyButton = closest(e.target, "[data-copy-phrase]");
        if (!copyButton) return;
        var phrase = copyButton.dataset.copyPhrase;
        var done = function () {
          if (status) status.textContent = "Copied: " + phrase;
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(phrase).then(done).catch(done);
        } else {
          done();
        }
      });

      if (routeSelect && routeOutput) {
        routeSelect.addEventListener("change", function () {
          routeOutput.textContent = routes[routeSelect.value] || "Choose what is happening now.";
        });
      }
    });
  }

  function explainerData() {
    var node = document.getElementById("playbook-explainers");
    if (!node) return {};
    try { return JSON.parse(node.textContent); } catch (e) { return {}; }
  }

  function initExplainers() {
    var data = explainerData();
    var outputs = Array.prototype.slice.call(document.querySelectorAll("[data-explainer-output]"));
    if (!outputs.length) return;

    function render(key) {
      var item = data[key];
      if (!item) return;
      outputs.forEach(function (output) {
        if (output.dataset.explainerOutput !== "all" && output.dataset.explainerOutput !== item.group) return;
        output.innerHTML = "<h3>" + item.title + "</h3><p>" + item.body + "</p>" + (item.action ? "<p><strong>Use it when:</strong> " + item.action + "</p>" : "");
      });
      document.querySelectorAll("[data-explainer]").forEach(function (el) {
        el.classList.toggle("active", el.dataset.explainer === key);
      });
    }

    document.addEventListener("click", function (e) {
      var trigger = closest(e.target, "[data-explainer]");
      if (trigger) render(trigger.dataset.explainer);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var trigger = closest(e.target, "[data-explainer]");
      if (!trigger) return;
      e.preventDefault();
      render(trigger.dataset.explainer);
    });

    var first = document.querySelector("[data-explainer]");
    if (first) render(first.dataset.explainer);
  }

  function initChoicePanels() {
    document.querySelectorAll("[data-choice-panel]").forEach(function (panel) {
      var output = panel.querySelector("[data-choice-output]");
      panel.querySelectorAll("[data-choice]").forEach(function (button) {
        button.addEventListener("click", function () {
          panel.querySelectorAll("[data-choice]").forEach(function (b) { b.classList.remove("active"); });
          button.classList.add("active");
          if (output) {
            output.innerHTML = "<strong>" + button.dataset.choiceTitle + "</strong><br>" + button.dataset.choiceBody;
          }
        });
      });
    });
  }

  function initChecklists() {
    document.querySelectorAll("[data-checklist]").forEach(function (list) {
      var output = list.querySelector("[data-checklist-output]");
      var checks = Array.prototype.slice.call(list.querySelectorAll("input[type='checkbox']"));
      function update() {
        var done = checks.filter(function (check) { return check.checked; }).length;
        if (output) output.textContent = done + " of " + checks.length + " checks satisfied";
      }
      checks.forEach(function (check) { check.addEventListener("change", update); });
      update();
    });
  }

  function initTierSimulator() {
    document.querySelectorAll("[data-tier-select]").forEach(function (select) {
      var output = document.querySelector(select.dataset.tierSelect);
      var tiers = {
        planning: "Tier 1: ephemeral. Keep it during the build, then archive it at ship.",
        adr: "Tier 2: decision. Promote it to an ADR when it is hard to reverse, surprising, and a real trade-off.",
        living: "Tier 3: living doc. Keep it present-tense and update it as the project changes.",
        generated: "Generated output. Treat it as derived; patch only when the source pipeline is unavailable."
      };
      select.addEventListener("change", function () {
        if (output) output.textContent = tiers[select.value] || "Choose a document type.";
      });
    });
  }

  function init() {
    initGlossary();
    initSectionNav();
    initPhraseTool();
    initExplainers();
    initChoicePanels();
    initChecklists();
    initTierSimulator();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
