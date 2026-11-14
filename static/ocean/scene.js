/* ==========================================================
   scene.js —— 海边的适配层
   不动 index.html 里原来的代码，只在它上面加一层：
       · 底部字幕条（她说的话，来自父窗口）
       · 六个贝壳 + 一个玻璃瓶（可点的热点）
       · 水面点击
       · 十分钟没动作 → 她自己动一下
       · 退出按钮
   所有动作通过 postMessage 发给父窗口，由父窗口写库。
   ========================================================== */
(() => {
  "use strict";

  const CTX = window.__SCENE_CTX || { key: "beach", user: "", persona: "" };

  /* 直接把动作发给后端，不等父窗口。
     后端返回一句台词和结算后的状态。 */
  async function post(action, extra) {
    if (!CTX.user || !CTX.persona) {
      console.log("[scene] 没有 user/persona，跳过", action);
      return null;
    }
    try {
      const r = await fetch("/api/scene/act", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({
          key: CTX.key, user: CTX.user, persona: CTX.persona, action: action
        }, extra || {}))
      });
      const d = await r.json();
      return d;
    } catch (e) {
      console.log("[scene] 请求失败", e);
      return null;
    }
  }

  /* ---------------- 字幕条 ---------------- */
  const cap = document.createElement("div");
  cap.id = "sceneCap";
  cap.innerHTML = '<span class="who"></span><span class="what"></span>';
  document.body.appendChild(cap);

  const whoEl = cap.querySelector(".who");
  const whatEl = cap.querySelector(".what");

  let capTimer = null;
  function say(who, text, holdMs) {
    whoEl.textContent = who || "";
    whatEl.textContent = text || "";
    cap.classList.add("on");
    clearTimeout(capTimer);
    capTimer = setTimeout(() => cap.classList.remove("on"), holdMs || 5200);
  }

  /* ---------------- 样式 ---------------- */
  const style = document.createElement("style");
  style.textContent = `
    #sceneCap{
      position:fixed; left:0; right:0; bottom:0;
      padding:18px 20px calc(18px + env(safe-area-inset-bottom)) 20px;
      background:linear-gradient(180deg, rgba(6,12,22,0) 0%, rgba(6,12,22,.78) 42%, rgba(6,12,22,.92) 100%);
      color:#eef6ff;
      font-family:"Songti SC","Noto Serif SC",serif;
      font-size:17px; line-height:1.85; letter-spacing:.06em;
      opacity:0; transform:translateY(12px);
      transition:opacity .5s ease, transform .5s ease;
      pointer-events:none; z-index:9998;
    }
    #sceneCap.on{ opacity:1; transform:none; }
    #sceneCap .who{
      display:block; font-size:11px; letter-spacing:.3em;
      color:rgba(160,205,255,.75); margin-bottom:.5em;
    }
    #sceneCap .what{ display:block; }

    .scHot{
      position:fixed; z-index:9997; cursor:pointer;
      border-radius:50%;
      background:radial-gradient(circle, rgba(180,225,255,.16) 0%, rgba(180,225,255,0) 70%);
      transition:transform .3s ease, background .3s ease;
      -webkit-tap-highlight-color:transparent;
    }
    .scHot:hover{ transform:scale(1.35); background:radial-gradient(circle, rgba(200,235,255,.3) 0%, rgba(200,235,255,0) 72%); }
    .scHot.found{ opacity:0; pointer-events:none; transition:opacity .6s ease; }

    #sceneHud{
      position:fixed; left:16px; top:16px; z-index:9999;
      display:flex; gap:10px; align-items:center;
      font-family:"Songti SC","Noto Serif SC",serif;
      font-size:11.5px; letter-spacing:.22em;
      color:rgba(190,225,255,.72);
      pointer-events:none;
    }
    #sceneHud b{ font-weight:400; color:#bfe8ff; }

    /* 原版底部的「浅海生灵」卡组会让底部三样东西撞在一起，收起来 */
    #dock{ display:none !important; }

    #sceneExit{
      position:fixed; left:16px; top:16px; z-index:9999;
      padding:.6em 1.3em; border-radius:100px; cursor:pointer;
      background:rgba(255,255,255,.07);
      border:1px solid rgba(160,210,255,.28);
      color:rgba(230,244,255,.9);
      font-family:inherit; font-size:12.5px; letter-spacing:.2em;
      backdrop-filter:blur(10px);
      transition:.3s;
      -webkit-tap-highlight-color:transparent;
    }
    #sceneExit:hover{ background:rgba(160,210,255,.16); border-color:rgba(160,210,255,.55); }
    #sceneExit:active{ transform:scale(.96); }

    /* ---------- 她：背影剪影 ---------- */
    #herSil{
      position:fixed; z-index:9996; pointer-events:none;
      left:50%; bottom:150px; transform:translateX(-50%);
      width:min(38vw, 200px);
      animation: herBreathe 6.4s ease-in-out infinite;
      filter:drop-shadow(0 14px 30px rgba(0,20,50,.55));
    }
    @keyframes herBreathe{
      0%,100%{ transform:translateX(-50%) translateY(0) scale(1); }
      50%    { transform:translateX(-50%) translateY(-3px) scale(1.008); }
    }
    #herSil .body{ fill:#141c2b; }
    #herSil .hair{ fill:#0d1420; }
    #herSil .rim{ fill:none; stroke:rgba(150,200,255,.16); stroke-width:1.2; }
    #herSil .strand{ fill:none; stroke:rgba(160,205,255,.10); stroke-width:1.1; stroke-linecap:round; }
    #herSil .hairg{ transform-origin:100px 90px; animation: hairSway 8.5s ease-in-out infinite; }
    @keyframes hairSway{
      0%,100%{ transform:rotate(0deg); }
      50%    { transform:rotate(1.6deg); }
    }

    /* ---------- 状态点 ---------- */
    #herDot{
      position:fixed; left:16px; top:60px; z-index:9999;
      display:flex; align-items:center; gap:8px;
      font-family:"Songti SC","Noto Serif SC",serif;
      font-size:11px; letter-spacing:.24em;
      color:rgba(190,225,255,.62);
      pointer-events:none;
    }
    #herDot i{
      width:7px; height:7px; border-radius:50%;
      background:#6fb7ff; box-shadow:0 0 12px 2px rgba(110,185,255,.6);
      transition:background .6s ease, box-shadow .6s ease;
    }

    /* ---------- 四句可以说的话 ---------- */
    #sceneAsk{
      position:fixed; left:0; right:0; z-index:9999;
      bottom:calc(92px + env(safe-area-inset-bottom));
      display:flex; gap:8px; justify-content:center;
      flex-wrap:wrap; padding:0 14px;
      pointer-events:auto;
    }
    .askBtn{
      padding:.62em 1.15em; border-radius:100px; cursor:pointer;
      background:rgba(255,255,255,.06);
      border:1px solid rgba(160,210,255,.24);
      color:rgba(226,242,255,.86);
      font-family:"Songti SC","Noto Serif SC",serif;
      font-size:12.5px; letter-spacing:.14em;
      backdrop-filter:blur(10px);
      transition:transform .14s ease, background .26s ease,
                 border-color .26s ease, box-shadow .26s ease;
      -webkit-tap-highlight-color:transparent;
    }
    .askBtn:hover{
      background:rgba(160,210,255,.14);
      border-color:rgba(160,210,255,.5);
      box-shadow:0 4px 18px rgba(90,170,255,.2);
    }
    .askBtn:active{ transform:scale(.96); box-shadow:none; }
    .askBtn:disabled{ opacity:.35; cursor:default; }

    @media (max-width:480px){
      #sceneCap{ font-size:15.5px; padding:14px 16px calc(14px + env(safe-area-inset-bottom)) 16px; }
      #sceneExit{ padding:.55em 1.1em; font-size:11.5px; }
      #herSil{ width:44vw; bottom:172px; }
      #herDot{ top:52px; font-size:10px; }
      #sceneAsk{ bottom:calc(112px + env(safe-area-inset-bottom)); gap:6px; }
      .askBtn{ padding:.55em .95em; font-size:11.5px; letter-spacing:.1em; }
    }

    @media (prefers-reduced-motion:reduce){
      #herSil, #herSil .hairg{ animation:none; }
    }
  `;
  document.head.appendChild(style);

  /* ---------------- HUD ---------------- */
  const hud = document.createElement("div");
  hud.id = "sceneHud";
  hud.innerHTML = '贝壳 <b id="scShell">0</b> / 6';
  document.body.appendChild(hud);
  const shellEl = document.getElementById("scShell");

  /* ---------------- 退出 ---------------- */
  const exit = document.createElement("button");
  exit.id = "sceneExit";
  exit.textContent = "回去";
  exit.addEventListener("click", async () => {
    const d = await post("leave");
    say("她", (d && d.line) || "路上小心。", 1400);
    setTimeout(() => {
      // 一定要回新界面 /app，不能靠 history.back ——
      // 从别处直接打开的场景页 history 可能指回旧界面 /。
      window.location.href = "/app";
    }, 1100);
  });
  document.body.appendChild(exit);

  /* ---------------- 她：背影剪影 ---------------- */
  const sil = document.createElement("div");
  sil.id = "herSil";
  sil.innerHTML = `
  <svg viewBox="0 0 200 240" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
      <linearGradient id="herRim" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#9ccfff" stop-opacity=".26"/>
        <stop offset="60%" stop-color="#9ccfff" stop-opacity=".05"/>
        <stop offset="100%" stop-color="#9ccfff" stop-opacity="0"/>
      </linearGradient>
    </defs>

    <!-- 头发（后面那一层） -->
    <g class="hairg">
      <path class="hair" d="M100 62
        C 132 62 150 86 150 116
        C 150 152 146 186 140 214
        L 60 214
        C 54 186 50 152 50 116
        C 50 86 68 62 100 62 Z"/>
    </g>

    <!-- 肩与背 -->
    <path class="body" d="M100 96
      C 128 96 146 118 148 152
      C 150 186 152 214 152 240
      L 48 240
      C 48 214 50 186 52 152
      C 54 118 72 96 100 96 Z"/>

    <!-- 头顶 -->
    <ellipse class="hair" cx="100" cy="92" rx="30" ry="33"/>

    <!-- 一点轮廓光 -->
    <path class="rim" d="M100 59 C 132 59 150 84 150 116
      C 150 150 147 182 142 208"/>

    <!-- 几缕碎发 -->
    <path class="strand" d="M128 78 C 138 100 140 132 136 160"/>
    <path class="strand" d="M74 80 C 64 104 62 136 66 162"/>
    <path class="strand" d="M100 62 C 100 90 101 118 100 140"/>

    <!-- 前面的膝盖（抱膝） -->
    <ellipse class="body" cx="72" cy="232" rx="26" ry="18"/>
    <ellipse class="body" cx="128" cy="232" rx="26" ry="18"/>
  </svg>`;
  document.body.appendChild(sil);

  /* ---------------- 状态点 ---------------- */
  const dot = document.createElement("div");
  dot.id = "herDot";
  dot.innerHTML = '<i></i><span></span>';
  document.body.appendChild(dot);
  const dotI = dot.querySelector("i");
  const dotT = dot.querySelector("span");

  function showState(st) {
    if (!st) return;
    const e = st.energy === undefined ? 0.6 : st.energy;
    const color = e >= 0.6 ? "#6fb7ff" : (e >= 0.25 ? "#8fb4cf" : "#5d6b7e");
    dotI.style.background = color;
    dotI.style.boxShadow = "0 0 12px 2px " + color + "88";
    dotT.textContent = (st.mood_label || "") + " · " + (st.energy_label || "");
  }

  /* ---------------- 四句可以对她说的话 ---------------- */
  const ASKS = [
    { key: "ask_cold",  label: "你冷不冷" },
    { key: "ask_stay",  label: "我陪你坐会儿" },
    { key: "ask_watch", label: "你在看什么" },
    { key: "ask_leave", label: "我该走了" },
  ];

  const askBar = document.createElement("div");
  askBar.id = "sceneAsk";
  ASKS.forEach((a) => {
    const b = document.createElement("button");
    b.className = "askBtn";
    b.textContent = a.label;
    b.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (b.disabled) return;
      b.disabled = true;
      const d = await post(a.key);
      if (d && d.line) say("她", d.line, 5600);
      if (d && d.state) showState(d.state);
      setTimeout(() => { b.disabled = false; }, 1600);
    });
    askBar.appendChild(b);
  });
  document.body.appendChild(askBar);

  /* ---------------- 贝壳 ---------------- */
  const SHELL_SPOTS = [
    { x: 0.18, y: 0.62 }, { x: 0.34, y: 0.74 }, { x: 0.51, y: 0.58 },
    { x: 0.66, y: 0.79 }, { x: 0.79, y: 0.64 }, { x: 0.88, y: 0.82 },
  ];
  let found = 0;

  SHELL_SPOTS.forEach((spot, i) => {
    const el = document.createElement("div");
    el.className = "scHot";
    el.style.width = "46px";
    el.style.height = "46px";
    el.style.left = "calc(" + (spot.x * 100) + "% - 23px)";
    el.style.top = "calc(" + (spot.y * 100) + "% - 23px)";
    el.dataset.i = i;
    el.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (el.classList.contains("found")) return;
      el.classList.add("found");
      found++;
      shellEl.textContent = String(found);
      const d = await post(found >= 6 ? "shell_all" : "shell");
      if (d && d.line) say("她", d.line, 5200);
    });
    document.body.appendChild(el);
  });

  /* ---------------- 玻璃瓶（石头缝里） ---------------- */
  const bottle = document.createElement("div");
  bottle.className = "scHot";
  bottle.style.width = "40px";
  bottle.style.height = "40px";
  bottle.style.left = "calc(10% - 20px)";
  bottle.style.top = "calc(84% - 20px)";
  let bottleTaken = false;
  bottle.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    if (bottleTaken) return;
    bottleTaken = true;
    bottle.classList.add("found");
    const d = await post("bottle");
    say("她", (d && d.line) || "……这个不该在这儿。", 6000);
  });
  document.body.appendChild(bottle);

  /* ---------------- 水面点击 ---------------- */
  let lastWater = 0;
  document.body.addEventListener("click", async (ev) => {
    if (ev.target.closest(".scHot") || ev.target.closest("#sceneExit")) return;
    const now = Date.now();
    if (now - lastWater < 8000) return;      // 别刷屏
    lastWater = now;
    const d = await post("water");
    if (d && d.line) say("她", d.line, 4200);
  });

  /* ---------------- 十分钟没动作 ---------------- */
  let idleTimer = null;
  function resetIdle() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(async () => {
      const d = await post("idle_10m");
      say("她", (d && d.line) || "（她动了一下）", 5000);
      resetIdle();
    }, 10 * 60 * 1000);
  }
  ["click", "pointermove", "touchstart", "keydown"].forEach((e) => {
    document.addEventListener(e, resetIdle, { passive: true, once: false });
  });
  resetIdle();

  /* ---------------- 进场：问后端要一句开场 ---------------- */
  (async () => {
    const d = await post("enter");
    const ent = d && d.entrance;
    if (ent && ent.state) showState(ent.state);
    if (ent && ent.line) {
      setTimeout(() => say("她", ent.line, 9000), 900);
    }
  })();
})();
