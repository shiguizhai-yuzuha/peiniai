/* 小暖 · 演示 v2：装配（把状态、画面、真实调用接起来） */

(function () {
  const S = window.XNDemoScript, D = window.XNDemo, V = window.XNDemoView, L = window.XNDemoLive;

  // API 基址（app.js 里的常量可能是旧值，这里统一）
  window.XN_API = window.XN_API || "https://peiniai.cn/xn";

  let bound = false;
  let lastIdx = -1;

  function bind() {
    if (bound) return;
    bound = true;

    V.buildBar();

    const on = function (id, evt, fn) {
      const el = document.getElementById(id);
      if (!el) return;
      const clone = el.cloneNode(true);
      el.parentNode.replaceChild(clone, el);
      clone.addEventListener(evt, fn);
    };

    on("demoNext", "click", function () { D.next(); });
    on("demoPause", "click", function () { D.pause(); V.setPauseLabel(D.paused); });
    on("demoSkip", "click", function () {
      if (D.mode === "live") { D.stop(); V.clearAll(); V.mountBar(false); return; }
      D.enterLive();
    });
    on("demoExitBtn", "click", function () { D.stop(); V.clearAll(); V.mountBar(false); });
    on("demoLiveBtn", "click", function () { D.enterLive(); });
    on("demoLiveSend", "click", send);
    on("demoLiveInp", "keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); send(); } });
    on("famClose", "click", function () { const o = document.getElementById("famOv"); if (o) o.hidden = true; });

    document.addEventListener("keydown", function (e) {
      const mode = D.mode;
      if (mode === "idle") return;
      if (e.key === "Escape") { D.stop(); V.clearAll(); V.mountBar(false); return; }
      if (e.key === "ArrowRight") { D.next(); }
      if (e.key === " ") { e.preventDefault(); D.pause(); V.setPauseLabel(D.paused); }
    });

    // 状态 → 画面
    D.on("enter", function (snap) {
      lastIdx = -1;
      setLiveBar(false);
      // 兜底：关掉开场层，避免盖住演示
      const ov = document.getElementById("introOv"), fr = document.getElementById("introFr");
      if (fr) fr.src = "about:blank";
      if (ov) ov.hidden = true;
      V.clearAll();
      V.mountBar(true);
      document.body.classList.add("demoing");
      V.caption("演示开始", 0, snap.total);
    });

    D.on("step", function (p) {
      if (p.idx === lastIdx) return;   // 同一步只画一次（防连点重复）
      lastIdx = p.idx;
      const step = p.step;
      V.caption(step.cap, p.idx, p.total);
      if (step.kind === "user" || step.kind === "ai") {
        V.bubble(step.kind, step.text, step.kind === "ai");
        return;
      }
      const d = step.data || {};
      switch (step.fx) {
        case "memory": V.memory(d); break;
        case "event": V.eventCard(d); break;
        case "proactive": V.bubbleNow("pro", d.text); V.bump("tbPro"); break;
        case "reminder": V.reminder(d); break;
        case "ringSoon": V.ring("soon"); break;
        case "ringDue": V.ring("due"); break;
        case "ack": V.ack(); break;
        case "elder": V.elder(); break;
        case "style": V.style(d.name); break;
        case "facts": V.facts(); break;
        case "family": D.enterFamily(); break;
        case "live": D.enterLive(); break;
        default: break;
      }
    });

    D.on("family", function () {
      V.family();
      clearTimeout(window._xnFamGuard);
      window._xnFamGuard = setTimeout(function () {
        if (D.mode === "family") D.enterLive();
      }, 5200);
    });
    D.on("live", function () {
      lastIdx = -1;
      setLiveBar(true);
      V.live();
      try { localStorage.setItem("xn_seen_intro", "1"); } catch (e) {}
    });
    D.on("exit", function () {
      document.body.classList.remove("demoing");
      V.clearAll();
      V.mountBar(false);
    });

    // 入口
    const hook = function (id, fn) {
      const el = document.getElementById(id);
      if (!el) return;
      const clone = el.cloneNode(true);
      el.parentNode.replaceChild(clone, el);
      clone.addEventListener("click", fn);
    };
    hook("mDemo", function () {
      const s = document.getElementById("sheetbg");
      if (s) s.hidden = true;
      D.startPpt();
      const ov = document.getElementById("introOv"), fr = document.getElementById("introFr");
      if (ov && fr) { fr.src = "intro.html?embed=1&v=" + Date.now(); ov.hidden = false; }
    });
    hook("topIntro", function () {
      const ov = document.getElementById("introOv"), fr = document.getElementById("introFr");
      if (ov && fr) { fr.src = "intro.html?embed=1&v=" + Date.now(); ov.hidden = false; }
    });
  }

  function setLiveBar(on) {
    const n = document.getElementById("demoNext");
    const p2 = document.getElementById("demoPause");
    const l = document.getElementById("demoLiveBtn");
    const sk = document.getElementById("demoSkip");
    [n, p2, l].forEach(function (b) {
      if (!b) return;
      b.disabled = !!on;
      b.style.opacity = on ? "0.35" : "";
      b.style.pointerEvents = on ? "none" : "";
    });
    if (sk) sk.textContent = on ? "结束" : "跳过";
  }

  async function send() {
    const inp = document.getElementById("demoLiveInp");
    const btn = document.getElementById("demoLiveSend");
    if (!inp || !btn || btn.disabled) return;
    const text = String(inp.value || "").trim();
    if (!text) return;
    btn.disabled = true;
    inp.value = "";

    V.bubbleNow("user", text);
    const row = document.createElement("div");
    row.className = "drow ai";
    const b = document.createElement("div");
    b.className = "dbubble";
    b.textContent = "…";
    row.appendChild(b);
    document.getElementById("said").appendChild(row);
    V.scroll();

    const r = await L.send(text);
    b.innerHTML = "";
    if (r.ok) {
      b.appendChild(document.createTextNode(r.reply || "（空）"));
      const tag = document.createElement("span");
      tag.className = "liveTag";
      tag.textContent = "真实 · " + r.ms + " ms";
      b.appendChild(tag);
      L.memories().then(function (items) {
        const bm = document.getElementById("tbMem");
        if (bm) bm.textContent = String(items.length);
      });
      // 实时展示“她抽到了什么”
      setTimeout(function(){ (async function () {
        try {
          const uid = encodeURIComponent(L.uid());
          const r = await fetch((window.XN_API || "https://peiniai.cn/xn") + "/facts?uid=" + uid, { cache: "no-store" });
          const d = await r.json();
          const kinds = (d && d.kinds) || {};
          const label = { name: "名字", people: "人物", events: "事件", plans: "计划",
                          health: "身体", likes: "喜欢", dislikes: "不喜欢", promises: "承诺" };
          const chips = [];
          Object.keys(label).forEach(function (k) {
            (kinds[k] || []).slice(0, 2).forEach(function (x) {
              chips.push('<i>' + label[k] + ' · ' + String(x.val || x).slice(0, 18) + '</i>');
            });
          });
          if (!chips.length) return;
          const line = document.createElement("div");
          line.className = "liveFacts";
          line.innerHTML = '<b>她抽到了</b>' + chips.join("");
          row.appendChild(line);
          V.scroll();
        } catch (e) {}
      })(); }, 2600);
    } else {
      b.appendChild(document.createTextNode(L.copy.offline));
      const tag = document.createElement("span");
      tag.className = "liveTag";
      tag.textContent = L.copy.offlineTag + (r.status ? " · " + r.status : "");
      b.appendChild(tag);
    }
    btn.disabled = false;
    V.scroll();
  }

  // intro iframe 通知进入演示
  window.addEventListener("message", function (e) {
    if (!e || !e.data || e.data.type !== "xn-enter-demo") return;
    const ov = document.getElementById("introOv"), fr = document.getElementById("introFr");
    if (fr) fr.src = "about:blank";
    if (ov) ov.hidden = true;
    try { localStorage.setItem("xn_seen_intro", "1"); } catch (er) {}
    D.start();
  });

  document.addEventListener("DOMContentLoaded", function () {
    bind();
    if (/[?&]demo=1/.test(location.search)) setTimeout(function () { D.start(); }, 300);
  });

  window.XNDemoBoot = bind;
})();
