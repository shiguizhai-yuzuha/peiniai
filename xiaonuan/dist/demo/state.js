/* 小暖 · 演示 v2：状态机（只管流程，不管画面） */

window.XNDemo = (function () {
  const S = window.XNDemoScript;
  const T = S.TIMING;
  const CO = S.COPY;

  const st = {
    mode: "idle",      // idle | ppt | script | family | live | done
    idx: 0,
    paused: false,
    timer: 0,
    saved: null,
    listeners: {}
  };

  function on(evt, fn) {
    (st.listeners[evt] = st.listeners[evt] || []).push(fn);
    return function () {
      st.listeners[evt] = (st.listeners[evt] || []).filter(function (f) { return f !== fn; });
    };
  }

  function emit(evt, payload) {
    (st.listeners[evt] || []).forEach(function (fn) {
      try { fn(payload); } catch (e) { console.warn("[demo]", evt, e); }
    });
  }

  function snapshot() {
    return {
      mode: st.mode,
      idx: st.idx,
      total: S.STEPS.length,
      paused: st.paused,
      step: S.STEPS[st.idx] || null
    };
  }

  function clearTimer() {
    if (st.timer) { clearTimeout(st.timer); st.timer = 0; }
  }

  function saveState() {
    st.saved = {
      style: document.documentElement.dataset.style || "",
      elder: document.documentElement.dataset.elder || "",
      scroll: (document.querySelector(".mid") || {}).scrollTop || 0
    };
  }

  function restoreState() {
    const v = st.saved || {};
    if (v.style) {
      if (window.setStyle) window.setStyle(v.style);
      else document.documentElement.dataset.style = v.style;
    }
    if (v.elder === "1") document.documentElement.dataset.elder = "1";
    else delete document.documentElement.dataset.elder;
    const mid = document.querySelector(".mid");
    if (mid) mid.scrollTop = v.scroll || 0;
    st.saved = null;
  }

  function start(opts) {
    if (st.mode !== "idle" && st.mode !== "done") stop(true);
    opts = opts || {};
    saveState();
    st.mode = "script";
    st.idx = 0;
    st.paused = false;
    document.documentElement.dataset.demo = "1";
    emit("enter", snapshot());
    step();
  }

  function startPpt() {
    if (st.mode !== "idle" && st.mode !== "done") stop(true);
    saveState();
    st.mode = "ppt";
    st.idx = 0;
    document.documentElement.dataset.demo = "1";
    emit("enter", snapshot());
  }

  function step() {
    if (st.mode !== "script") return;
    if (st.idx >= S.STEPS.length) { enterLive(); return; }
    const cur = S.STEPS[st.idx];
    emit("step", { idx: st.idx, step: cur, snap: snapshot() });
    if (cur.kind === "fx" && cur.fx === "live") { enterLive(); return; }
    schedule(cur);
  }

  function schedule(cur) {
    clearTimer();
    const wait = Math.round((cur.wait || T.stepBase) * T.slowFactor);
    st.timer = setTimeout(function () {
      if (st.paused) { waitResume(); return; }
      st.idx += 1;
      step();
    }, wait);
  }

  function waitResume() {
    clearTimer();
    st.timer = setTimeout(function () {
      if (st.paused) waitResume();
      else { st.idx += 1; step(); }
    }, 220);
  }

  function next() {
    if (st.mode !== "script") return;
    clearTimer();
    st.idx += 1;
    step();
  }

  function pause() {
    if (st.mode !== "script") return;
    st.paused = !st.paused;
    if (!st.paused) { clearTimer(); step(); }
    emit("state", snapshot());
  }

  function enterFamily() {
    if (st.mode !== "script") return;
    st.mode = "family";
    emit("family", snapshot());
    clearTimer();
    st.timer = setTimeout(function () {
      if (st.mode === "family") { st.mode = "script"; st.idx += 1; step(); }
    }, T.familyHold);
  }

  function enterLive() {
    clearTimer();
    st.mode = "live";
    st.paused = false;
    emit("live", snapshot());
  }

  function jump(n) {
    if (st.mode !== "script") return;
    st.idx = Math.max(0, Math.min(S.STEPS.length - 1, n));
    step();
  }

  function stop(silent) {
    clearTimer();
    st.mode = "idle";
    st.paused = false;
    st.idx = 0;
    document.documentElement.dataset.demo = "0";
    try {
      ["demo_state", "demo_mem", "demo_rem"].forEach(function (k) { localStorage.removeItem(k); });
    } catch (e) {}
    if (!silent) restoreState();
    emit("exit", snapshot());
  }

  return {
    start: start, startPpt: startPpt, next: next, pause: pause, jump: jump, stop: stop,
    enterFamily: enterFamily, enterLive: enterLive,
    on: on, snapshot: snapshot,
    get mode() { return st.mode; },
    get paused() { return st.paused; }
  };
})();
