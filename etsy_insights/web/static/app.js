// Etsy Insights — small helpers for buttons, forms and live session status.
(function () {
  "use strict";
  var token = (document.querySelector('meta[name="app-token"]') || {}).content || "";

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-App-Token": token },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }

  function showErrors(root, data) {
    root.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    var general = root.querySelector("[data-error]");
    if (general) general.textContent = "";
    var errors = data.errors || {};
    Object.keys(errors).forEach(function (name) {
      var el = root.querySelector('[data-error-for="' + name + '"]');
      if (el) el.textContent = errors[name];
    });
    if (data.error) {
      if (general) general.textContent = data.error; else alert(data.error);
    }
  }

  // Forms that post to the API
  document.querySelectorAll("form[data-api]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var body = {};
      new FormData(form).forEach(function (value, key) { body[key] = value; });
      post(form.getAttribute("data-api"), body).then(function (r) {
        if (r.ok) { location.reload(); } else { showErrors(form, r.data); }
      });
    });
  });

  // Buttons that post to the API (Prioritize, Remove, …)
  document.querySelectorAll("button[data-api]").forEach(function (button) {
    button.addEventListener("click", function () {
      var body = JSON.parse(button.getAttribute("data-body") || "{}");
      button.disabled = true;
      post(button.getAttribute("data-api"), body).then(function (r) {
        if (r.ok) { location.reload(); } else { button.disabled = false; alert(r.data.error || "Something went wrong."); }
      });
    });
  });

  function startSession(body) {
    post("/api/session/start", body).then(function (r) {
      if (!r.ok) alert(r.data.error || "The session could not start.");
      refresh();
    });
  }

  document.querySelectorAll("[data-start]").forEach(function (button) {
    button.addEventListener("click", function () { startSession(JSON.parse(button.getAttribute("data-start"))); });
  });

  var ignore = document.querySelector("[data-ignore-cooldown]");
  if (ignore) {
    ignore.addEventListener("click", function () {
      var answer = prompt("Etsy recently showed a warning. Running now adds risk to your account.\nType YES to run anyway:");
      if (answer === null) return;
      startSession({ test_run: false, ignore_cooldown: true, confirm: answer.trim() });
    });
  }

  var stop = document.querySelector("[data-stop]");
  if (stop) {
    stop.addEventListener("click", function () {
      stop.disabled = true;
      stop.textContent = "Stopping…";
      post("/api/session/stop", {}).then(refresh);
    });
  }

  function showQuit() {
    document.body.innerHTML = '<main class="quit"><h1>Etsy Insights has quit.</h1>' +
      '<p class="muted">Open it again from Applications.</p></main>';
  }

  var quit = document.querySelector("[data-quit]");
  if (quit) {
    quit.addEventListener("click", function () {
      post("/api/quit", {}).then(function (r) {
        if (r.ok) return showQuit();
        if (r.status === 409 && confirm(r.data.error)) {
          post("/api/quit", { confirm: true }).then(function (r2) { if (r2.ok) showQuit(); });
        }
      });
    });
  }

  // Live status on the Session page
  var root = document.querySelector("[data-status-root]");
  var failures = 0;

  function setText(selector, text) {
    var el = root.querySelector(selector);
    if (el) el.textContent = text;
  }

  function render(s) {
    var r = s.runner;
    setText("[data-today]", s.today.searches);
    setText("[data-collected]", s.collected);
    setText("[data-queue]", s.queue);
    var account = root.querySelector("[data-account]");
    account.className = "card card--" + s.account.state;
    setText("[data-account-message]", s.account.message);
    root.querySelectorAll("[data-start]").forEach(function (b) { b.disabled = !s.can_start; });
    var blocker = root.querySelector("[data-blocker]");
    blocker.hidden = !s.blocker || r.running;
    if (s.blocker) blocker.firstChild.textContent = s.blocker + " ";
    if (ignore) ignore.hidden = s.account.state !== "cooldown";
    root.querySelector("[data-running]").hidden = !r.running;
    if (r.running) {
      setText("[data-running-title]", r.source === "terminal" ? "A session is running (started from Terminal)" : "Session is running");
      if (stop) {
        stop.hidden = r.source === "terminal";
        stop.disabled = r.stopping;
        stop.textContent = r.stopping ? "Stopping…" : "Stop";
      }
      setText("[data-progress-text]", "Search " + r.done + " of " + (r.limit || "…"));
      root.querySelector("[data-progress-bar]").style.width = (r.limit ? (100 * r.done / r.limit) : 0) + "%";
      setText("[data-current]", r.current_keyword || "…");
      var log = root.querySelector("[data-log]");
      log.innerHTML = "";
      r.log_tail.forEach(function (line) {
        var li = document.createElement("li");
        li.textContent = line;
        log.appendChild(li);
      });
      log.scrollTop = log.scrollHeight;
    }
    var last = root.querySelector("[data-last]");
    if (s.last_session) {
      last.innerHTML = "";
      var p1 = document.createElement("p");
      p1.innerHTML = "<strong></strong> searches · ";
      p1.firstChild.textContent = s.last_session.checked;
      p1.appendChild(document.createTextNode(s.last_session.started_at.slice(0, 16).replace("T", " ")));
      var p2 = document.createElement("p");
      p2.className = "muted";
      p2.textContent = s.last_session.reason_text;
      last.appendChild(p1);
      last.appendChild(p2);
    }
  }

  function refresh() {
    if (!root) return;
    fetch("/api/status").then(function (res) { return res.json(); }).then(function (s) {
      failures = 0;
      document.querySelector("[data-offline]").hidden = true;
      render(s);
    }).catch(function () {
      failures += 1;
      if (failures >= 3) document.querySelector("[data-offline]").hidden = false;
    });
  }

  if (root) setInterval(refresh, 2000);
})();
