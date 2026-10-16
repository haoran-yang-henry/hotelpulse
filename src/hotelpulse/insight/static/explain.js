(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var state = { id: null };

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function params(lang) {
    var p = new URLSearchParams(location.search);
    if (lang) p.set("lang", lang);
    return p;
  }

  function render(data) {
    var n = data.narrative, v = data.verification, m = data.meta;
    state.id = data.explanation_id;
    var facts = {};
    data.facts.forEach(function (f) { facts[f.id] = f.text; });

    $("dashboard").textContent = data.chart.dashboard;
    $("title").textContent = data.chart.title;
    $("filters").textContent = data.filters.join(" · ");
    $("headline").textContent = n.headline;

    var badge = $("badge");
    if (m.mode === "template") {
      badge.textContent = "Facts only - no AI used";
      badge.className = "badge neutral";
    } else if (v.verified) {
      badge.textContent = "✓ All " + v.numbers_checked + " numbers verified against the chart's data";
      badge.className = "badge ok";
    } else {
      badge.textContent = "⚠ Not found in the data: " + v.unverified.join(", ");
      badge.className = "badge warn";
    }

    var obs = $("observations"); obs.replaceChildren();
    n.observations.forEach(function (o) {
      var li = el("li", o.text);
      o.fact_ids.forEach(function (id) {
        var tag = el("span", id, "fact-ref");
        tag.title = facts[id] || "";
        li.appendChild(tag);
      });
      obs.appendChild(li);
    });

    var causes = $("causes"); causes.replaceChildren();
    n.possible_causes.forEach(function (c) {
      var li = el("li", c.text);
      li.appendChild(el("span", c.confidence, "confidence " + c.confidence));
      causes.appendChild(li);
    });
    $("causes-card").hidden = !n.possible_causes.length;

    var actions = $("actions"); actions.replaceChildren();
    n.recommended_actions.forEach(function (a) { actions.appendChild(el("li", a)); });

    var caveats = $("caveats"); caveats.replaceChildren();
    n.caveats.forEach(function (c) { caveats.appendChild(el("li", c)); });
    $("caveats-card").hidden = !n.caveats.length;

    var table = $("facts"); table.replaceChildren();
    data.facts.forEach(function (f) {
      var tr = el("tr");
      tr.appendChild(el("td", f.id, "fid"));
      tr.appendChild(el("td", f.kind, "kind"));
      tr.appendChild(el("td", f.text));
      table.appendChild(tr);
    });

    var parts = [m.mode === "llm" ? m.model : "template", (m.latency_ms / 1000).toFixed(1) + " s"];
    if (m.cache_hit) parts.push("from cache");
    if (m.prompt_tokens) parts.push(m.prompt_tokens + " + " + m.completion_tokens + " tokens");
    $("meta").textContent = parts.join(" · ");
    $("thanks").hidden = true;

    document.querySelectorAll("[data-lang]").forEach(function (b) {
      b.classList.toggle("active", b.dataset.lang === m.lang);
    });
    $("loading").hidden = true;
    $("result").hidden = false;
  }

  function load(lang) {
    $("loading").hidden = false;
    $("error").hidden = true;
    fetch("/api/explain?" + params(lang).toString())
      .then(function (r) {
        return r.json().then(function (body) {
          if (!r.ok) throw new Error(body.detail || ("HTTP " + r.status));
          return body;
        });
      })
      .then(function (data) {
        render(data);
        if (lang) history.replaceState(null, "", "?" + params(lang).toString());
      })
      .catch(function (e) {
        $("loading").hidden = true;
        $("error").hidden = false;
        $("error").textContent = "Could not explain this chart: " + e.message;
      });
  }

  document.querySelectorAll("[data-lang]").forEach(function (b) {
    b.addEventListener("click", function () { load(b.dataset.lang); });
  });
  document.querySelectorAll("[data-helpful]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (!state.id) return;
      fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation_id: state.id, helpful: b.dataset.helpful === "true" })
      }).then(function () { $("thanks").hidden = false; });
    });
  });
  load(new URLSearchParams(location.search).get("lang"));
})();
