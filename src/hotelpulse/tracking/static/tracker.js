/*!
 * HotelPulse tracker v1 - first-party, consent-first, batched.
 *
 * <script>window.hpPage = {type: "home", events: [{name: "...", properties: {...}}]};</script>
 * <script src="https://collector.example/tracker.js" defer></script>
 *
 * Nothing is sent - and no visitor cookie is set - before the visitor accepts analytics
 * cookies. Events recorded before the decision wait in memory and are sent on "accept"
 * or dropped on "reject".
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var ENDPOINT = (script && script.dataset.endpoint) || new URL("/collect", script.src).href;
  var CONSENT_COOKIE = "hp_consent";
  var VISITOR_COOKIE = "hp_aid";
  var SESSION_KEY = "hp_session";
  var SESSION_TTL_MS = 30 * 60 * 1000;
  var MAX_BATCH = 100;

  var queue = [];
  var undecided = [];
  var timer = null;

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function setCookie(name, value, days) {
    document.cookie = name + "=" + encodeURIComponent(value) + "; Max-Age=" + days * 86400 +
      "; Path=/; SameSite=Lax";
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, function (c) {
      return (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16);
    });
  }

  function consent() {
    return getCookie(CONSENT_COOKIE); // "granted" | "denied" | null
  }

  function visitorId() {
    var id = getCookie(VISITOR_COOKIE) || uuid();
    setCookie(VISITOR_COOKIE, id, 395); // refresh expiry on every visit
    return id;
  }

  function sessionHint() {
    var now = Date.now();
    var session = null;
    try { session = JSON.parse(localStorage.getItem(SESSION_KEY)); } catch (e) { /* ignore */ }
    if (!session || now - session.last > SESSION_TTL_MS) session = { id: uuid(), last: now };
    session.last = now;
    try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch (e) { /* ignore */ }
    return session.id;
  }

  function build(name, properties) {
    return {
      schema_version: 1,
      event_id: uuid(),
      event_name: name,
      event_ts: new Date().toISOString(),
      page_url: location.href,
      referrer: document.referrer || null,
      locale: navigator.language || null,
      screen: window.screen ? screen.width + "x" + screen.height : null,
      properties: properties || {}
    };
  }

  function enqueue(event, immediately) {
    event.anonymous_id = visitorId();
    event.session_hint = sessionHint();
    queue.push(event);
    if (immediately || queue.length >= 20) flush();
    else if (!timer) timer = setTimeout(flush, 1000);
  }

  function flush() {
    clearTimeout(timer);
    timer = null;
    while (queue.length) {
      var batch = queue.splice(0, MAX_BATCH);
      var sentAt = new Date().toISOString();
      batch.forEach(function (e) { e.sent_at = sentAt; });
      var body = JSON.stringify({ events: batch });
      // text/plain keeps this a CORS "simple request": no preflight, sendBeacon-compatible
      var sent = navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, new Blob([body], { type: "text/plain" }));
      if (!sent) {
        fetch(ENDPOINT, { method: "POST", body: body, keepalive: true, headers: { "Content-Type": "text/plain" } })
          .catch(function () { /* analytics must never break the page */ });
      }
    }
  }

  // options.beacon: send right away - use it for clicks that navigate away, because a page
  // that is being unloaded may never get to run the batching timer
  function track(name, properties, options) {
    var state = consent();
    var event = build(name, properties);
    if (state === "granted") enqueue(event, options && options.beacon);
    else if (state === null) undecided.push(event);
    // "denied": drop silently
  }

  function setConsent(granted) {
    setCookie(CONSENT_COOKIE, granted ? "granted" : "denied", 180);
    var waiting = undecided;
    undecided = [];
    if (granted) {
      waiting.forEach(enqueue);
      flush();
    } else {
      setCookie(VISITOR_COOKIE, "", 0);
    }
  }

  // flush whatever is queued when the page goes away (no single event is reliable everywhere)
  addEventListener("pagehide", flush);
  addEventListener("beforeunload", flush);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });

  window.hp = { track: track, setConsent: setConsent, consent: consent, flush: flush };

  // Events declared by the server-rendered page
  var page = window.hpPage || {};
  track("page_view", { page_type: page.type || "other" });
  (page.events || []).forEach(function (e) { track(e.name, e.properties); });
})();
