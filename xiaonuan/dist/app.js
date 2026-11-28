/* 小暖 · 脚本（拆自 simple.html） */

/* 五期：?demo=1&selftest=1 时统计 API fetch 次数（只观察，不改演示脚本） */
(function(){
  const q = location.search;
  if (!/[?&]demo=1(?:&|$)/.test(q) || !/[?&]selftest=1(?:&|$)/.test(q)) return;
  window.__xnApi = [];
  const orig = window.fetch;
  window.fetch = function(input){
    try {
      const u = String(typeof input === "string" ? input : (input && input.url) || "");
      if (u.indexOf("/functions/v1/app") >= 0 || u.indexOf("/api/") >= 0) window.__xnApi.push(u);
    } catch(e){}
    return orig.apply(this, arguments);
  };
})();

/* ===== */

const $ = function (id){ return document.getElementById(id); };
const API = "https://peiniai.cn/xn";
const GO_LOGIN = "/login.html?next=" + encodeURIComponent(location.pathname);

/* ---------- 演示模式状态（T6-T10） ---------- */
const DEMO = {
  free: false,
  on: false,   /* v2：旧演示停用，由 demo/ 模块接管 */
  paused: false,
  idx: 0,
  timer: 0,
  memT: 0,
  savedElder: "0",
  savedFont: "1",
  savedStyle: ""
};

/* ---------- 匿名访客（T3）：不弹注册，自动建客 ---------- */
function ensureGuestId(){
  let id = lsGet("uid", "");
  if (!id || id.slice(0, 2) !== "g_"){
    id = "g_" + (window.crypto && crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, "")
      : Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
    lsSet("uid", id);
  }
  return id;
}
async function bootSession(){
  try {
    const r = await fetch(API + "/auth/guest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guestId: ensureGuestId() })
    });
    if (!r.ok){
      const d = await r.json().catch(function (){ return {}; });
      if (d.code === "RATE") toast("新访客太多了，明天再来。");
    }
  } catch (e){}
}
(function gate(){
  if (DEMO.on) return;
  fetch(API + "/auth/me", { cache: "no-store" }).then(function (r){
    if (r.status === 401) bootSession();
  }).catch(function (){});
})();
const said = $("said"), hint = $("hint"), talk = $("talk"),
      inp = $("inp"), wxLine = $("wx"), toastEl = $("toast");

const SR = (window.isSecureContext === false) ? null
  : (window.SpeechRecognition || window.webkitSpeechRecognition);

/* ---------- 本地状态 + 后台 state 表（ui.*） ---------- */
function lsGet(k, d){
  try { var v = localStorage.getItem("xiaonuan." + k); return v == null ? d : v; }
  catch (e){ return d; }
}
function lsSet(k, v){
  try { localStorage.setItem("xiaonuan." + k, String(v)); } catch (e){}
}
function stateWrite(k, v){
  if (DEMO.on) return;
  lsSet(k, v);
  try {
    fetch(API + "/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ k: "ui." + k, v: String(v) })
    }).catch(function (){});
  } catch (e){}
}

let fsScale = parseFloat(lsGet("font", "1")) || 1;
let ttsOn = lsGet("tts", "1") !== "0";

/* ---------- 四期：风格系统（20 主题） ---------- */
const STYLES = ["paper","xuan","warm","night","swiss","morandi","salt","forest",
  "caramel","film","blueprint","sakura","cyber","clay","indigo","matcha",
  "sunset","snow","brick","pixel"];

function lumOf(hex){
  const m = String(hex || "").replace("#", "").trim();
  const h = m.length === 3 ? m.replace(/./g, "$&$&") : m;
  if (h.length !== 6) return 0.5;
  const c = [0, 2, 4].map(function(i){
    const v = parseInt(h.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratioOf(l1, l2){
  const hi = Math.max(l1, l2), lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}
/* 按钮字自动反色：白/深两色取对比度高的那个。
   不用「亮度>0.5」：0.19~0.5 区间会误选白字（暖阳 3.54 不够 4.5）。 */
function btnFgOf(name, brand){
  const lb = lumOf(brand);
  const dark = (name === "cyber" || name === "film") ? "#000" : "#111";
  return ratioOf(lb, 1) >= ratioOf(lb, lumOf(dark)) ? "#fff" : dark;
}

function setStyle(name, save){
  if (STYLES.indexOf(name) < 0) name = "paper";
  document.documentElement.dataset.style = name;
  const br = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim();
  document.documentElement.style.setProperty("--btn-fg", btnFgOf(name, br));
  if (save !== false) lsSet("style", name);
  document.querySelectorAll(".stycard").forEach(function(el){
    el.classList.toggle("on", el.dataset.s === name);
  });
}

function loadStyle(){
  const qs = /[?&]style=([a-z]+)/.exec(location.search);
  setStyle(qs ? qs[1] : lsGet("style", "paper"), !qs);
}

/* 开启老人模式时，若用户没手动选过风格，自动切暖阳 */
function maybeElderStyle(){
  if (lsGet("style", "") === "") setStyle("warm");
}

function buildStyleGrid(){
  const box = $("stygrid");
  if (!box || box.dataset.done) return;
  box.dataset.done = "1";
  const names = {paper:"纸墨",xuan:"宣纸",warm:"暖阳",night:"夜航",swiss:"瑞士",
    morandi:"莫兰迪",salt:"海盐",forest:"森林",caramel:"焦糖",film:"胶片",
    blueprint:"图纸",sakura:"樱",cyber:"赛博",clay:"陶土",indigo:"靛蓝",
    matcha:"抹茶",sunset:"落日",snow:"雪原",brick:"砖红",pixel:"像素"};
  STYLES.forEach(function(s){
    const d = document.createElement("button");
    d.type = "button";
    d.className = "stycard";
    d.dataset.s = s;
    d.innerHTML = '<i data-s="' + s + '"></i><span>' + names[s] + '</span>';
    d.onclick = function(){ setStyle(s); };
    box.appendChild(d);
  });
  setStyle(document.documentElement.dataset.style || "paper", false);
}

function applyFont(){
  document.body.style.setProperty("--fs", String(fsScale));
  document.body.setAttribute("data-elder", fsScale > 1 ? "1" : "0");
  if (fsScale > 1 && !DEMO.on) maybeElderStyle();
}
applyFont();
loadStyle();

/* ---------- 问候与天气（先出字，不等接口） ---------- */
function greetNow(){
  const h = new Date().getHours();
  if (h >= 5 && h < 8) return "早上好";
  if (h >= 8 && h < 11) return "上午好";
  if (h >= 11 && h < 13) return "中午好";
  if (h >= 13 && h < 18) return "下午好";
  if (h >= 18 && h < 22) return "晚上好";
  return "还没睡呀";
}
$("gree").textContent = greetNow();

function paintDate(){
  const n = new Date();
  const p = function(x){ return String(x).padStart(2, "0"); };
  $("dateLine").textContent = (n.getMonth() + 1) + "月" + n.getDate() + "日 周" +
    "日一二三四五六"[n.getDay()] + " " + p(n.getHours()) + ":" + p(n.getMinutes());
}
paintDate();
setInterval(paintDate, 60000);

function toast(text, ms){
  if (!text) return;
  toastEl.textContent = text;
  toastEl.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(function (){ toastEl.hidden = true; }, ms || 1600);
}

async function loadCtx(){
  if (DEMO.on) return;
  try {
    const r = await fetch(API + "/context", { cache: "no-store" });
    if (!r.ok) return;
    const d = await r.json();
    const w = d && d.weather;
    if (!w || w.t == null) return;
    const t = Math.round(Number(w.t));
    if (!isFinite(t)) return;
    const tone = t < 18 ? "有点凉" : (t <= 27 ? "正好" : "有点热");
    wxLine.textContent = "今天 " + t + " 度，" + tone + "。";
    wxLine.hidden = false;
  } catch (e){}
}
loadCtx();

/* ---------- 五状态机 ---------- */
const LEGAL = {
  IDLE:   ["LISTEN", "CARD"],
  LISTEN: ["THINK", "IDLE", "ERROR"],
  THINK:  ["IDLE", "ERROR"],
  CARD:   ["IDLE"],
  ERROR:  ["IDLE"]
};
let state = "IDLE";

function setState(next){
  if (next === state) return true;
  const ok = (LEGAL[state] || []).indexOf(next) >= 0;
  if (!ok){
    try { console.warn("非法状态", state, "→", next); } catch (e){}
    return false;
  }
  state = next;
  paintState();
  return true;
}

let saidIsRetry = false;

function paintState(){
  document.body.classList.toggle("carding", state === "CARD");
  const lock = state === "CARD";
  talk.disabled = lock;
  $("kb").disabled = lock;
  $("more").disabled = lock;
  if (state === "LISTEN"){
    setSaid("我在听");
    hint.textContent = "松手就发";
    hint.hidden = false;
  } else if (state === "THINK"){
    setSaid("她说……");
    hint.hidden = true;
  } else if (state === "CARD"){
    hint.hidden = true;
  } else if (state === "ERROR"){
    hint.hidden = true;
  } else {
    hint.textContent = "按住说话";
    hint.hidden = !micOk;
  }
}

function setSaid(text, retry){
  said.textContent = text || "";
  saidIsRetry = !!retry;
  said.classList.toggle("retry", !!retry);
  if (retry){
    said.setAttribute("role", "button");
    said.setAttribute("tabindex", "0");
  } else {
    said.removeAttribute("role");
    said.removeAttribute("tabindex");
  }
}

function toThink(){
  if (state === "IDLE") setState("LISTEN");
  return setState("THINK");
}

/* ---------- 朗读 ---------- */
let voice = null, audioUnlocked = false;

function loadVoices(){
  if (!("speechSynthesis" in window)) return;
  const vs = speechSynthesis.getVoices() || [];
  const zh = vs.filter(function (v){ return /^zh|cmn|chinese/i.test(v.lang || ""); });
  voice = zh.find(function (v){
    return /female|ting|xiao|hui|yao|mei|lan|女/i.test(v.name || "");
  }) || zh[0] || null;
}
if ("speechSynthesis" in window){
  loadVoices();
  speechSynthesis.onvoiceschanged = loadVoices;
}
function stopSpeak(){
  if (!("speechSynthesis" in window)) return;
  try { speechSynthesis.cancel(); } catch (e){}
}
function speak(t){
  if (!ttsOn || !audioUnlocked || !t || !("speechSynthesis" in window)) return;
  if (!speechSynthesis.getVoices().length) return;
  stopSpeak();
  const u = new SpeechSynthesisUtterance(t);
  u.lang = "zh-CN";
  u.rate = 0.9;
  if (voice) u.voice = voice;
  try { speechSynthesis.speak(u); } catch (e){}
}
document.addEventListener("pointerdown", function (){
  if (!audioUnlocked){
    audioUnlocked = true;
    stateWrite("mic_unlocked", "1");
  }
}, true);

/* 提醒到点的唯一提示音 */
let actx = null;
function ding(){
  if (!audioUnlocked) return;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    actx = actx || new AC();
    const o = actx.createOscillator(), g = actx.createGain();
    o.type = "sine";
    o.frequency.value = 880;
    g.gain.value = 0.06;
    o.connect(g);
    g.connect(actx.destination);
    o.start();
    o.stop(actx.currentTime + 0.18);
  } catch (e){}
}

/* ---------- 说话 ---------- */
let rec = null, listening = false, micOk = !!SR;
let heldAt = 0, got = false, gotText = "", wantSend = false,
    sent = false, holdTimer = 0, autoStop = false;

if (!SR){
  talk.classList.add("micfail");
  hint.hidden = true;
}

function micFail(){
  micOk = false;
  listening = false;
  wantSend = false;
  clearTimeout(holdTimer);
  talk.classList.add("micfail");
  hint.hidden = true;
  if (state === "LISTEN") setState("IDLE");
  setSaid("");
}

function buildRec(){
  rec = new SR();
  rec.lang = "zh-CN";
  rec.interimResults = false;
  rec.continuous = false;
  rec.onresult = function (e){
    let t = "";
    try { t = ((e.results && e.results[0] && e.results[0][0] &&
      e.results[0][0].transcript) || "").trim(); } catch (err){}
    if (t){
      got = true;
      gotText = t;
    }
    if (wantSend) finishAndSend();
  };
  rec.onerror = function (e){
    const why = (e && (e.error || "")) || "";
    if (why === "not-allowed" || why === "service-not-allowed"){
      micFail();
      return;
    }
    if (!got) speechError();
  };
  rec.onend = function (){
    listening = false;
    clearTimeout(holdTimer);
    if (sent) return;
    if (wantSend) finishAndSend();
    else if (!got && state === "LISTEN") speechError();
  };
}

function startTalk(){
  if (busy || state !== "IDLE") return;
  stopSpeak();
  clearTimeout(errTimer);
  hideMiss();
  if (!micOk){
    showKb();
    return;
  }
  if (listening) return;
  got = false;
  gotText = "";
  wantSend = false;
  sent = false;
  autoStop = false;
  heldAt = Date.now();
  try {
    buildRec();
    rec.start();
    listening = true;
    if (!setState("LISTEN")){
      listening = false;
      try { rec.abort(); } catch (e){}
      return;
    }
    holdTimer = setTimeout(function (){
      if (state !== "LISTEN") return;
      autoStop = true;
      wantSend = true;
      toast("说完了，我记下了", 1600);
      try { rec.stop(); } catch (e){}
    }, 15000);
  } catch (e){
    micFail();
  }
}

function finishAndSend(){
  if (sent) return;
  if (got && gotText){
    sent = true;
    clearTimeout(holdTimer);
    if (listening){ try { rec.stop(); } catch (e){} }
    sendText(gotText);
  } else {
    speechError();
  }
}

function shortTap(){
  listening = false;
  wantSend = false;
  clearTimeout(holdTimer);
  try { if (rec) rec.abort(); } catch (e){}
  if (state === "LISTEN") setState("IDLE");
  setSaid("");
  toast("按住久一点。", 1600);
}

/* ---------- 没听清 ---------- */
let errTimer = 0;

function showMiss(){
  $("miss").hidden = false;
}
function hideMiss(){
  $("miss").hidden = true;
  clearTimeout(errTimer);
}
function speechError(){
  listening = false;
  wantSend = false;
  clearTimeout(holdTimer);
  if (state === "LISTEN") setState("ERROR");
  else if (state !== "ERROR") setState("ERROR");
  setSaid("");
  showMiss();
  clearTimeout(errTimer);
  errTimer = setTimeout(function (){
    hideMiss();
    if (state === "ERROR") setState("IDLE");
  }, 3000);
}

$("again").addEventListener("click", function (){
  hideMiss();
  if (state === "ERROR") setState("IDLE");
  if (!micOk){ showKb(); return; }
  startTalk();
  /* 这一次说完整句再停：不用按住，识别自己会结束 */
  if (listening){
    setTimeout(function (){
      if (state === "LISTEN" && !got){ wantSend = true; }
      if (state === "LISTEN" && got){ wantSend = true; finishAndSend(); }
    }, 800);
  }
});
$("toKb").addEventListener("click", function (){
  hideMiss();
  if (state === "ERROR") setState("IDLE");
  showKb();
});

if (SR){
  talk.addEventListener("pointerdown", function (e){
    if (!micOk){ e.preventDefault(); showKb(); return; }
    if (busy || state !== "IDLE") return;
    e.preventDefault();
    startTalk();
  });
  talk.addEventListener("pointerup", function (e){
    if (!SR || !micOk) return;
    e.preventDefault();
    if (state !== "LISTEN") return;
    if (autoStop) return;
    const held = Date.now() - heldAt;
    if (held < 400){
      shortTap();
    } else {
      wantSend = true;
      if (got) finishAndSend();
    }
  });
  talk.addEventListener("pointercancel", function (){
    if (state === "LISTEN") shortTap();
  });
  talk.addEventListener("pointerleave", function (){
    if (state === "LISTEN"){
      const held = Date.now() - heldAt;
      if (held < 400) shortTap();
      else { wantSend = true; if (got) finishAndSend(); }
    }
  });
  talk.addEventListener("click", function (){
    if (!micOk) showKb();
  });
} else {
  talk.addEventListener("click", showKb);
}

/* ---------- 打字 ---------- */
function showKb(){
  document.body.classList.add("typing");
  $("typebox").hidden = false;
  $("kb").textContent = "收起键盘";
  inp.focus();
}
function hideKb(){
  document.body.classList.remove("typing");
  $("typebox").hidden = true;
  $("kb").textContent = "想打字？";
  inp.blur();
}
$("kb").addEventListener("click", function (){
  if ($("typebox").hidden) showKb();
  else hideKb();
});
$("send").addEventListener("click", function (){ sendText(inp.value); });

inp.addEventListener("input", function (){
  inp.style.height = "auto";
  inp.style.height = Math.min(inp.scrollHeight, 88) + "px";
});
inp.addEventListener("keydown", function (e){
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing){
    e.preventDefault();
    sendText(inp.value);
  }
});

/* ---------- 发送 ---------- */
let busy = false, lastText = "";

function replyText(r){
  if (Array.isArray(r)){
    return r.map(function (x){
      return typeof x === "string" ? x : ((x && x.t) || "");
    }).filter(Boolean).join("\n");
  }
  return String(r == null ? "" : r);
}

/* ---------- 危机出口：三级三个，二级一个 ---------- */
function hideCrisis(){
  const box = $("crisis"), msg = $("cmsg");
  box.hidden = true;
  box.textContent = "";
  msg.hidden = true;
  msg.textContent = "";
  document.body.classList.remove("crisis-on");
}

function showCrisis(c){
  hideCrisis();
  const lv = c ? Number(c.level || 0) : 0;
  if (lv < 2) return;
  if (typeof hideKb === "function") hideKb();
  document.body.classList.add("crisis-on");
  const box = $("crisis");
  const kinds = lv >= 3
    ? [["hotline", "帮我打 12356"], ["family", "告诉家人"], ["nearby", "附近看看"]]
    : [["family", "告诉家人"]];
  kinds.forEach(function (p){
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = p[1];
    b.addEventListener("click", function (){ crisisExit(p[0]); });
    box.appendChild(b);
  });
  box.hidden = false;
}

async function crisisExit(kind){
  if (DEMO.on) return;
  const msg = $("cmsg");
  msg.hidden = false;
  msg.textContent = "……";
  try {
    const r = await fetch(API + "/crisis/exit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: kind, uid: "" })
    });
    const d = await r.json();
    msg.textContent = (d && d.ok) ? (d.show || "好。") : "这条路走不通";
  } catch (e){
    msg.textContent = "这条路走不通";
  }
}

function pushHist(text){
  const h = document.getElementById("hist");
  if (!h) return;
  const row = document.createElement("div");
  row.className = "hrow user";
  const b = document.createElement("div");
  b.className = "hb";
  b.textContent = String(text || "");
  row.appendChild(b);
  h.appendChild(row);
  h.scrollTop = h.scrollHeight;
}

async function sendText(text, fromRetry){
  if (DEMO.on) return;
  const t = String(text || "").trim();
  if (!t || busy) return;
  if (state === "CARD") return;
  hideCrisis();
  hideMiss();
  if (fromRetry){
    if (state === "ERROR") setState("IDLE");
  } else {
    inp.value = "";
    inp.style.height = "";
  }
  lastText = t;
  pushHist(t);
  if (!toThink()) return;
  busy = true;
  let d = null, netErr = false;
  try {
    const r = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: t, uid: (function(){ try { return localStorage.getItem("uid") || "judge"; } catch(e){ return "judge"; } })() })
    });
    try { d = await r.json(); } catch (e){ netErr = true; }
  } catch (e){
    netErr = true;
  }
  busy = false;

  if (netErr){
    sendFailed();
    return;
  }
  if (!d || !d.ok){
    const msg = (d && d.error) || "";
    if (msg && msg !== "空"){
      if (state === "THINK") setState("IDLE");
      setSaid(msg);
      stopSpeak();
      return;
    }
    sendFailed();
    return;
  }

  if (state === "THINK") setState("IDLE");
  const out = replyText(d.reply);
  setSaid(out);
  speak(out);
  showCrisis(d.crisis);
  updateTodayBar();
}

function sendFailed(){
  if (state === "THINK") setState("ERROR");
  setSaid("没发出去，点一下重发", true);
  stopSpeak();
}

said.addEventListener("click", function (){
  if (saidIsRetry) sendText(lastText, true);
});
said.addEventListener("keydown", function (e){
  if (saidIsRetry && (e.key === "Enter" || e.key === " ")){
    e.preventDefault();
    sendText(lastText, true);
  }
});

/* ---------- 提醒卡 ---------- */
let cardId = 0, cardAt = 0;

async function pollRem(){
  if (DEMO.on) return;
  if (state !== "IDLE" || busy || document.hidden) return;
  let d = null;
  try {
    const r = await fetch(API + "/reminders", { cache: "no-store" });
    if (!r.ok) return;
    d = await r.json();
  } catch (e){
    return;
  }
  if (state !== "IDLE" || busy) return;
  const items = (d && d.items) || [];
  const now = nowMs() / 1000;
  let due = null;
  for (let i = 0; i < items.length; i++){
    const x = items[i];
    if (!x.done && (!x.status || x.status === "live")
        && Number(x.snooze_until || 0) <= now
        && Number(x.at) <= now + 3){
      if (!due || Number(x.at) < Number(due.at)) due = x;
    }
  }
  if (due) openCard(due);
}

function openCard(item){
  cardId = Number(item.id || 0);
  cardAt = Number(item.at || 0);
  const late = (nowMs() / 1000) - cardAt > 300;
  $("ct").textContent = late ? "刚才到点了" : "到点了";
  $("ctime").textContent = item.hhmm || "";
  $("cw").textContent = item.what || "";
  ringItem = item;
  updateRing(item);
  clearInterval(ringTimer);
  ringTimer = setInterval(function (){ updateRing(ringItem); }, 30000);
  document.body.classList.add("carding");
  hideCrisis();
  $("cardwrap").hidden = false;
  hideKb();
  if (state !== "CARD") setState("CARD");
  talk.disabled = true;
  $("kb").disabled = true;
  stateWrite("card_open", "1");
  ding();
}

function closeCard(){
  $("cardwrap").hidden = true;
  document.body.classList.remove("carding");
  clearInterval(ringTimer);
  stateWrite("card_open", "0");
  if (state === "CARD") setState("IDLE");
  talk.disabled = false;
  $("kb").disabled = false;
}

function ack(action){
  if (DEMO.on) return;
  const id = cardId;
  closeCard();
  if (!id) return;
  try {
    fetch(API + "/reminder_ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id, action: action })
    }).catch(function (){});
  } catch (e){}
}
$("know").addEventListener("click", function (){ ack("know"); });
$("later").addEventListener("click", function (){ ack("later"); });

pollRem();
setInterval(pollRem, 15000);

/* ---------- 菜单（五项） ---------- */
function paintMenu(){
  $("mTts").textContent = ttsOn ? "朗读：开" : "朗读：关";
  $("mSize").textContent = fsScale > 1 ? "字小一点" : "字大一点";
}
function openStyle(){
  $("sheetbg").hidden = true;
  buildStyleGrid();
  $("stybg").hidden = false;
}
function autoIntroOnBoot(){
  try{
    if (localStorage.getItem("xn_seen_intro")) return;
    if (/[?&]demo=1/.test(location.search)) return;
    if (window.matchMedia("(orientation: portrait)").matches) return;
    setTimeout(function(){ openIntro(); }, 500);
  }catch(e){}
}
document.addEventListener("DOMContentLoaded", autoIntroOnBoot);


/* ── 演示中的真实对话 ── */
function demoRealSync(items){
  const list = $("memlist");
  if (!list || !items || !items.length) return;
  list.textContent = "";
  const tl = document.createElement("div");
  tl.className = "memtl";
  const g = document.createElement("div");
  g.className = "tlgroup";
  const h = document.createElement("div");
  h.className = "tlhead";
  h.textContent = "真实记忆";
  g.appendChild(h);
  items.slice(0, 8).forEach(function(it){
    const row = document.createElement("div");
    row.className = "tlitem";
    const dot = document.createElement("span");
    dot.className = "tldot";
    const body = document.createElement("div");
    body.className = "tlbody";
    const tx = document.createElement("div");
    tx.className = "tltext";
    tx.textContent = (it && (it.text || it.content)) || String(it);
    const meta = document.createElement("div");
    meta.className = "tlmeta";
    meta.textContent = "真实 · 刚刚";
    body.appendChild(tx); body.appendChild(meta);
    row.appendChild(dot); row.appendChild(body);
    g.appendChild(row);
  });
  tl.appendChild(g);
  list.appendChild(tl);
  const bm = $("tbMem");
  if (bm) bm.textContent = String(items.length);
}


function demoFamily(){
  const ov = $("famOv"), rows = $("famRows");
  if (!ov || !rows) return;
  const items = [...document.querySelectorAll(".tltext")].map(function(e){ return e.textContent.trim(); }).filter(Boolean);
  const memCount = items.length || 3;
  const list = [
    ["今天记住", memCount + " 件事"],
    ["提醒", "1 次（明天 08:00 去医院）"],
    ["主动开口", "1 次（收拾房间）"],
    ["情绪", "平稳"]
  ];
  rows.innerHTML = list.map(function(r){
    return '<div class="famrow"><b>' + r[0] + '</b><span>' + r[1] + '</span></div>';
  }).join("");
  ov.hidden = false;
  clearTimeout(demoFamily._t);
  demoFamily._t = setTimeout(function(){ ov.hidden = true; }, 3200);
}

function demoEnterFree(){
  DEMO.free = true;
  try { clearTimeout(DEMO.timer); DEMO.timer = 0; } catch(e){}
  DEMO.paused = true;
  demoLiveToggle(true);
  const cap = $("demoCapTxt");
  if (cap) cap.textContent = "轮到您了：随便说一句，走真实接口";
  demoBubbleNow("ai", "现在轮到您。随便说一句，比如「我下周三要复查」。");
}

function demoLiveToggle(show){
  const box = $("demoLive");
  if (!box) return;
  const v = (typeof show === "boolean") ? show : box.hidden;
  box.hidden = !v;
  if (v){
    const inp = $("demoLiveInp");
    if (inp) setTimeout(function(){ inp.focus(); }, 60);
  }
}

function demoLiveBadge(ms){
  return '<span class="liveTag">真实 · ' + Math.round(ms) + ' ms</span>';
}

async function demoLiveSend(){
  const inp = $("demoLiveInp");
  const btn = $("demoLiveSend");
  if (!inp || !btn) return;
  const text = String(inp.value || "").trim();
  if (!text || btn.disabled) return;
  btn.disabled = true;
  inp.value = "";

  demoBubbleNow("user", text);

  const row = document.createElement("div");
  row.className = "drow ai";
  const b = document.createElement("div");
  b.className = "dbubble";
  b.textContent = "…";
  row.appendChild(b);
  said.appendChild(row);
  demoScroll();

  const t0 = performance.now();
  try {
    const r = await fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    });
    const ms = performance.now() - t0;
    const raw = await r.text();
    let d = null;
    try { d = JSON.parse(raw); } catch (e){ d = null; }

    b.innerHTML = "";
    if (!d){
      b.appendChild(document.createTextNode("接口没连上（本地预览或未部署）"));
      b.insertAdjacentHTML("beforeend", '<span class="liveTag">离线</span>');
      return;
    }
    const reply = d.reply || d.text || d.show || (d.ok === false ? "（接口返回失败）" : "（空）");
    b.appendChild(document.createTextNode(String(reply)));
    b.insertAdjacentHTML("beforeend", demoLiveBadge(ms));
    if (DEMO.free){
      try {
        const ctx = d.context || d.memories;
        if (ctx) demoRealSync(ctx);
        else setTimeout(function(){ if (typeof loadMem === "function") loadMem(); }, 300);
      } catch(e){}
    }
  } catch (e){
    b.textContent = "连不上接口（" + (e && e.message ? e.message : "网络错误") + "）";
  } finally {
    btn.disabled = false;
    demoScroll();
  }
}

$("famClose").addEventListener("click", function(){ $("famOv").hidden = true; });
$("demoFree").addEventListener("click", function(){ demoEnterFree(); });
$("demoNext").addEventListener("click", function(){
  if (!DEMO.on) return;
  clearTimeout(DEMO.timer);
  DEMO.paused = false;
  demoStep();
});
$("demoLiveBtn").addEventListener("click", function(){ demoLiveToggle(); });
$("demoLiveSend").addEventListener("click", demoLiveSend);
$("demoLiveInp").addEventListener("keydown", function(e){
  if (e.key === "Enter"){ e.preventDefault(); demoLiveSend(); }
});

/* 演示结束/退出时收起 */
function demoLiveReset(){
  const box = $("demoLive");
  if (box) box.hidden = true;
  const inp = $("demoLiveInp");
  if (inp) inp.value = "";
}

function openIntro(){
  const ov = $("introOv"), fr = $("introFr");
  if (!ov || !fr) return;
  fr.src = "intro.html?embed=1";
  ov.hidden = false;
}
function closeIntro(demo){
  const ov = $("introOv"), fr = $("introFr");
  if (fr) fr.src = "about:blank";
  if (ov) ov.hidden = true;
  try { localStorage.setItem("xn_seen_intro", "1"); } catch(e){}
  if (demo && typeof demoStart === "function"){
    if (!DEMO.on) demoStart();
    else demoExit();
  }
}
window.addEventListener("message", function(e){
  /* v2：交给 demo/ 模块处理，旧路径停用 */
});
$("topIntro").addEventListener("click", openIntro);
$("introSkip").addEventListener("click", function(){ closeIntro(false); });
$("topFam").addEventListener("click", function(){ demoFamily(); });
$("topMem").addEventListener("click", function(){ openMem(); });
$("topStyle").addEventListener("click", function(){ openStyle(); });
$("more").addEventListener("click", function (){
  paintMenu();
  $("sheetbg").hidden = false;
});
$("mClose").addEventListener("click", function (){ $("sheetbg").hidden = true; });
$("sheetbg").addEventListener("click", function (e){
  if (e.target === $("sheetbg")) $("sheetbg").hidden = true;
});
$("mTts").addEventListener("click", function (){
  ttsOn = !ttsOn;
  stateWrite("read_aloud", ttsOn ? "1" : "0");
  if (!ttsOn) stopSpeak();
  paintMenu();
});
$("mSize").addEventListener("click", function (){
  fsScale = fsScale > 1 ? 1 : 1.15;
  stateWrite("font_scale", fsScale > 1 ? "1.15" : "1.0");
  applyFont();
  paintMenu();
});
$("mStyle").addEventListener("click", function (){
  $("sheetbg").hidden = true;
  buildStyleGrid();
  $("stybg").hidden = false;
});
$("styClose").addEventListener("click", function (){ $("stybg").hidden = true; });
$("stybg").addEventListener("click", function (e){
  if (e.target === $("stybg")) $("stybg").hidden = true;
});
paintMenu();

/* ---------- 首次进入：只说一次 ---------- */
if (!DEMO.on && lsGet("seen", "") !== "1"){
  setTimeout(function (){ toast("我是小暖。", 3200); }, 60);
  stateWrite("seen", "1");
}

/* ---------- 首次引导语：清缓存后首条换成引导 ---------- */
try {
  if (!DEMO.on && !localStorage.getItem("xn_seen")){
    $("said").textContent = "我是小暖。你有什么事，跟我说一遍，我就记住了。";
    localStorage.setItem("xn_seen", "1");
  }
} catch (e){}

/* ---------- 从后台补回开关（本机没有时） ---------- */
(async function syncState(){
  if (DEMO.on) return;
  try {
    const r = await fetch(API + "/state", { cache: "no-store" });
    if (!r.ok) return;
    const d = await r.json();
    const s = (d && d.state) || {};
    if (lsGet("seen", "") === "" && s["ui.seen"] === "1") lsSet("seen", "1");
    if (lsGet("tts", "") === "" && (s["ui.read_aloud"] === "0" || s["ui.read_aloud"] === "1")){
      ttsOn = s["ui.read_aloud"] !== "0";
      lsSet("tts", ttsOn ? "1" : "0");
      paintMenu();
    }
    if (lsGet("font", "") === "" && (s["ui.font_scale"] === "1.0" || s["ui.font_scale"] === "1.15")){
      fsScale = parseFloat(s["ui.font_scale"]) || 1;
      lsSet("font", String(fsScale));
      applyFont();
      paintMenu();
    }
  } catch (e){}
})();

/* ---------- 记忆抽屉 ---------- */
function fmtMemDate(ms){
  const d = new Date(Number(ms || 0) + 8 * 3600 * 1000);
  if (!isFinite(d.getTime())) return "";
  return (d.getUTCMonth() + 1) + "月" + d.getUTCDate() + "日";
}
async function loadFacts(){
  const box = document.getElementById("factsBox");
  if (!box) return;
  try {
    const uid = encodeURIComponent((function(){ try { return localStorage.getItem("uid") || "judge"; } catch(e){ return "judge"; } })());
    const r = await fetch((window.XN_API || "https://peiniai.cn/xn") + "/facts?uid=" + uid, { cache: "no-store" });
    const d = await r.json();
    const kinds = (d && d.kinds) || {};
    const label = {people:"人物", events:"事件", plans:"计划", health:"身体", likes:"喜欢", dislikes:"不喜欢", promises:"答应过", name:"名字"};
    const chips = [];
    Object.keys(label).forEach(function(k){
      const arr = kinds[k] || [];
      if (arr.length) chips.push('<span class="fk"><b>' + label[k] + '</b>' + arr.length + '</span>');
    });
    box.innerHTML = chips.length ? chips.join("") : '<span class="fempty">还没有抽取出结构化记忆</span>';
  } catch (e) {
    box.innerHTML = '<span class="fempty">记忆内核没连上</span>';
  }
}

async function loadMem(){
  if (DEMO.on && !DEMO.free) return;
  try { loadFacts(); } catch (e) {}
  const list = $("memlist");
  list.textContent = "";
  const l = document.createElement("div");
  l.className = "mempty";
  l.textContent = "正在想…";
  list.appendChild(l);
  let items = [];
  try {
    let r = await fetch(API + "/memories?uid=" + encodeURIComponent((function(){ try { return localStorage.getItem("uid") || "judge"; } catch(e){ return "judge"; } })()), { cache: "no-store" });
    if (r.status === 401 && typeof bootSession === "function"){
      console.warn("[记忆] 401，先建访客会话再重试");
      try { await bootSession(); } catch(e){}
      r = await fetch(API + "/memories?uid=" + encodeURIComponent((function(){ try { return localStorage.getItem("uid") || "judge"; } catch(e){ return "judge"; } })()), { cache: "no-store" });
    }
    if (!r.ok){
      console.warn("[记忆] HTTP " + r.status);
      throw new Error("HTTP " + r.status);
    }
    const d = await r.json();
    if (!d || d.ok === false){
      console.warn("[记忆] 接口返回", d && d.error);
      throw new Error((d && d.error) || "bad");
    }
    items = (d && d.items) || [];
  } catch(e){
    list.textContent = "";
    const el = document.createElement("div");
    el.className = "mempty";
    el.textContent = "读取失败，稍后再试";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mretry";
    b.textContent = "重试";
    b.addEventListener("click", loadMem);
    list.appendChild(el);
    list.appendChild(b);
    return;
  }
  list.textContent = "";
  if (!items.length){
    const e = document.createElement("div");
    e.className = "mempty";
    e.textContent = "她还没记住什么。跟她说一件家里的事试试。";
    list.appendChild(e);
    return;
  }
  renderEventCards(list, items);
  const MAX = 50;
  const shown = items.slice(0, MAX);
  const groups = [];
  shown.forEach(function(it){
    const key = tlGroupKey(Number(it.ts || 0));
    const g = groups[groups.length - 1];
    if (g && g.key === key) g.items.push(it);
    else groups.push({ key: key, items: [it] });
  });
  const tl = document.createElement("div");
  tl.className = "memtl";
  const ORDER = ["今天", "昨天", "本周", "更早"];
  groups.sort(function(a, b){ return ORDER.indexOf(a.key) - ORDER.indexOf(b.key); });
  let idx = 0;
  groups.forEach(function(g){
    const box = document.createElement("div");
    box.className = "tlgroup";
    const h = document.createElement("div");
    h.className = "tlhead";
    h.textContent = g.key;
    box.appendChild(h);
    g.items.forEach(function(it){
      const row = document.createElement("div");
      row.className = "tlitem";
      row.style.animationDelay = Math.min(idx, 10) * 40 + "ms";
      idx++;
      const dot = document.createElement("span");
      dot.className = "tldot";
      const body = document.createElement("div");
      body.className = "tlbody";
      const t = document.createElement("div");
      t.className = "tltext";
      t.textContent = String(it.text || "");
      t.title = String(it.text || "");
      t.addEventListener("click", function(){ t.classList.toggle("open"); });
      const m = document.createElement("div");
      m.className = "tlmeta";
      m.textContent = "说过 " + (Number(it.times) || 1) + " 次 · " + (it.when || fmtRel(Number(it.ts || 0)));
      body.appendChild(t);
      body.appendChild(m);
      row.appendChild(dot);
      row.appendChild(body);
      box.appendChild(row);
    });
    tl.appendChild(box);
  });
  list.appendChild(tl);
  if (items.length > MAX){
    const more = document.createElement("div");
    more.className = "tlmore";
    more.textContent = "还有 " + (items.length - MAX) + " 条";
    list.appendChild(more);
  }
}
function openMem(){
  const bg = $("membg");
  $("sheetbg").hidden = true;
  if (!bg.hidden) return;
  bg.hidden = false;
  requestAnimationFrame(function(){
    requestAnimationFrame(function(){ bg.classList.add("on"); });
  });
  loadMem();
  updateTodayBar();
}
function closeMem(){
  const bg = $("membg");
  if (bg.hidden) return;
  bg.classList.remove("on");
  setTimeout(function(){ bg.hidden = true; }, 280);
}
$("mMem").addEventListener("click", openMem);
$("memClose").addEventListener("click", closeMem);
$("membg").addEventListener("click", function(e){
  if (e.target === $("membg")) closeMem();
});
document.addEventListener("keydown", function(e){
  if (e.key === "Escape") closeMem();
});

/* ---------- 演示拨时间（仅 ?demo=clock） ---------- */
if (/[?&]demo=clock(?:&|$)/.test(location.search)){
  $("demoBox").hidden = false;
}
function demoISO(ms){
  const t = new Date(Number(ms) + 8 * 3600 * 1000);
  const p = function(n){ return String(n).padStart(2, "0"); };
  return t.getUTCFullYear() + "-" + p(t.getUTCMonth() + 1) + "-" + p(t.getUTCDate()) +
    " " + p(t.getUTCHours()) + ":" + p(t.getUTCMinutes());
}
async function demoPost(targetMs){
  if (DEMO.on) return;
  if (busy || state !== "IDLE") return;
  $("sheetbg").hidden = true;
  simNowMs = targetMs;
  try {
    const r = await fetch(API + "/proactive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ now: demoISO(targetMs) })
    });
    const d = await r.json();
    if (d && d.ok && d.say){
      setSaid(d.say);
      speak(d.say);
    } else {
      toast("她这会儿没有要说的", 2000);
    }
  } catch(e){
    toast("网络不太好", 1600);
  }
  showDemoCard();
}
async function firstLiveRem(){
  if (DEMO.on) return null;
  try {
    const r = await fetch(API + "/reminders", { cache: "no-store" });
    if (!r.ok) return null;
    const d = await r.json();
    const items = (d && d.items) || [];
    const now = Date.now() / 1000;
    for (let i = 0; i < items.length; i++){
      const x = items[i];
      if (!x.done && Number(x.at) > now) return x;
    }
    return null;
  } catch(e){
    return null;
  }
}
$("demoTmrw").addEventListener("click", function(){
  const t = new Date(Date.now() + 8 * 3600 * 1000);
  const base = Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate(), 7, 0, 0) - 8 * 3600 * 1000;
  demoPost(base + 24 * 3600 * 1000);
});
$("demoSoon").addEventListener("click", async function(){
  const x = await firstLiveRem();
  if (!x){ toast("还没有到点的提醒", 2000); return; }
  demoPost(Number(x.at) * 1000 - 3600 * 1000);
});
$("demoDue").addEventListener("click", async function(){
  const x = await firstLiveRem();
  if (!x){ toast("还没有到点的提醒", 2000); return; }
  demoPost(Number(x.at) * 1000);
});

/* ══════════ 二期可视化：A 时间轴 · D 数据条 · C 倒计时环 · B 事件卡片 ══════════ */
const BJ = 8 * 3600 * 1000;
let simNowMs = 0, ringItem = null, ringTimer = 0;
function nowMs(){ return simNowMs || Date.now(); }

function bjParts(ms){
  const d = new Date(Number(ms || 0) + BJ);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(),
           w: d.getUTCDay(), h: d.getUTCHours(), min: d.getUTCMinutes() };
}
function bjDayStart(ms){
  const p = bjParts(ms);
  return Date.UTC(p.y, p.m - 1, p.d) - BJ;
}
function bjTodayStart(){ return bjDayStart(Date.now()); }

/* A 记忆时间轴 */
function tlGroupKey(ts){
  const t0 = bjTodayStart();
  if (ts >= t0) return "今天";
  if (ts >= t0 - 86400000) return "昨天";
  const dow = bjParts(t0).w;
  const weekStart = t0 - ((dow + 6) % 7) * 86400000;
  if (ts >= weekStart) return "本周";
  return "更早";
}
function fmtRel(ts){
  if (!ts) return "";
  const now = Date.now() / 1000;
  const d = now - ts;
  if (d < 600) return "刚刚";
  if (d < 3600) return Math.round(d / 60) + " 分钟前";
  const dt = new Date(ts * 1000);
  const today = new Date();
  if (dt.toDateString() === today.toDateString()) return "今天 " + String(dt.getHours()).padStart(2, "0") + ":" + String(dt.getMinutes()).padStart(2, "0");
  const y = new Date(today.getTime() - 86400000);
  if (dt.toDateString() === y.toDateString()) return "昨天";
  return (dt.getMonth() + 1) + "月" + dt.getDate() + "日";
}

function fmtClock(ts){
  const p = bjParts(ts);
  return String(p.h).padStart(2, "0") + ":" + String(p.min).padStart(2, "0");
}

/* D 今日数据条 */
let tbCache = { mem: null, rem: null, pro: null };
function tbRestore(){
  try {
    const v = JSON.parse(lsGet("todaybar", "{}") || "{}");
    if (v && v.mem != null) return v;
  } catch(e){}
  return null;
}
function tbSet(id, v){
  const el = $(id);
  if (el.textContent === String(v)) return;
  el.textContent = v;
  el.classList.remove("pop");
  void el.offsetWidth;
  el.classList.add("pop");
}
async function updateTodayBar(){
  if (DEMO.on) return;
  let mem = null, rem = null, pro = null, anyOk = false;
  try {
    const r = await fetch(API + "/memories", { cache: "no-store" });
    if (r.ok){
      const d = await r.json();
      const items = (d && d.items) || [];
      const t0 = bjTodayStart();
      mem = items.filter(function(x){ return Number(x.ts || 0) >= t0; }).length;
      anyOk = true;
    }
  } catch(e){}
  try {
    const r = await fetch(API + "/family/summary", { cache: "no-store" });
    if (r.ok){
      const d = await r.json();
      const t = (d && d.today) || {};
      rem = Number(t.reminders) || 0;
      pro = Number(t.proactive) || 0;
      anyOk = true;
    }
  } catch(e){}
  if (anyOk){
    mem = mem == null ? (tbCache.mem == null ? 0 : tbCache.mem) : mem;
    rem = rem == null ? (tbCache.rem == null ? 0 : tbCache.rem) : rem;
    pro = pro == null ? (tbCache.pro == null ? 0 : tbCache.pro) : pro;
    tbCache = { mem: mem, rem: rem, pro: pro };
    lsSet("todaybar", JSON.stringify(tbCache));
    tbSet("tbMem", mem);
    tbSet("tbRem", rem);
    tbSet("tbPro", pro);
  } else {
    const c = tbRestore();
    if (c){
      tbSet("tbMem", c.mem); tbSet("tbRem", c.rem); tbSet("tbPro", c.pro);
    }
  }
}

/* C 提醒倒计时环 */
const RING_C = 113;
function updateRing(item){
  const fg = document.querySelector("#cardwrap .ring-fg");
  const txt = document.querySelector("#cardwrap .ringtxt");
  if (!fg || !item) return;
  const at = Number(item.at || 0) * 1000;
  const left = at - nowMs();
  const created = Number(item.created || item.ts || 0);
  const span = created > 0 ? Math.max(at - created, 60000) : 86400000;
  const p = Math.min(1, Math.max(0, left / span));
  fg.setAttribute("stroke-dashoffset", String((RING_C * (1 - p)).toFixed(1)));
  fg.classList.toggle("soon", left > 0 && left <= 3600000);
  fg.classList.toggle("due", left <= 0);
  if (txt){
    if (left <= 0) txt.textContent = "到点";
    else if (left < 3600000) txt.textContent = Math.max(1, Math.round(left / 60000)) + "m";
    else txt.textContent = Math.min(24, Math.round(left / 3600000)) + "h";
  }
}
async function showDemoCard(){
  if (DEMO.on) return;
  let items = [];
  try {
    const r = await fetch(API + "/reminders", { cache: "no-store" });
    if (!r.ok) return;
    const d = await r.json();
    items = (d && d.items) || [];
  } catch(e){ return; }
  if (!items.length){ toast("还没有到点的提醒", 2000); return; }
  const now = nowMs() / 1000;
  let pick = null;
  for (let i = 0; i < items.length; i++){
    const x = items[i];
    if (x.done) continue;
    if (!pick || Math.abs(Number(x.at) - now) < Math.abs(Number(pick.at) - now)) pick = x;
  }
  if (!pick){
    for (let i = 0; i < items.length; i++){
      const x = items[i];
      if (!pick || Math.abs(Number(x.at) - now) < Math.abs(Number(pick.at) - now)) pick = x;
    }
  }
  if (pick) openCard(pick);
  else toast("还没有到点的提醒", 2000);
}

/* B 事件卡片 */
const EV_WORDS = ["回来", "复查", "住院", "体检", "交费", "过生日"];
function evIsDone(id){
  try { return localStorage.getItem("xiaonuan.ev.done." + id) === "1"; } catch(e){ return false; }
}
function evSetDone(id){
  try { localStorage.setItem("xiaonuan.ev.done." + id, "1"); } catch(e){}
}
function evParseDate(text){
  const t = String(text || "");
  const t0 = bjTodayStart();
  const wk = { "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6 };
  let m;
  if (/大后天/.test(t)) return t0 + 3 * 86400000;
  if (/后天/.test(t)) return t0 + 2 * 86400000;
  if (/明天/.test(t)) return t0 + 86400000;
  if (/今天/.test(t)) return t0;
  m = t.match(/(?:下|后)(?:个)?(?:周|星期|礼拜)([一二三四五六日天])/);
  if (m){
    const dow = bjParts(t0).w;
    const weekStart = t0 - ((dow + 6) % 7) * 86400000;
    return weekStart + 7 * 86400000 + wk[m[1]] * 86400000;
  }
  m = t.match(/(?:周|星期|礼拜)([一二三四五六日天])/);
  if (m){
    const dow = bjParts(t0).w;
    const weekStart = t0 - ((dow + 6) % 7) * 86400000;
    const d = weekStart + wk[m[1]] * 86400000;
    return d < t0 ? d + 7 * 86400000 : d;
  }
  m = t.match(/(\d{1,2})月(\d{1,2})[日号]/);
  if (m){
    const p = bjParts(Date.now());
    const d = Date.UTC(p.y, Number(m[1]) - 1, Number(m[2])) - BJ;
    return d < t0 ? Date.UTC(p.y + 1, Number(m[1]) - 1, Number(m[2])) - BJ : d;
  }
  m = t.match(/(\d{1,2})[日号]/);
  if (m){
    const p = bjParts(Date.now());
    const day = Number(m[1]);
    const d = Date.UTC(p.y, p.m - 1, day) - BJ;
    return d < t0 ? Date.UTC(p.y, p.m, day) - BJ : d;
  }
  return 0;
}
function fmtEvDate(ms){
  const p = bjParts(ms);
  return p.m + "月" + p.d + "日 周" + "日一二三四五六"[p.w];
}
function evCard(ev, t0){
  const done = evIsDone(ev.id);
  const card = document.createElement("div");
  card.className = "evcard";
  if (done) card.classList.add("done");
  const d = document.createElement("div");
  d.className = "evdate";
  d.textContent = fmtEvDate(ev.date);
  const t = document.createElement("div");
  t.className = "evtext";
  t.textContent = ev.text;
  const s = document.createElement("div");
  const diff = Math.round((ev.date - t0) / 86400000);
  if (done){
    s.className = "evstate done";
    s.textContent = "已完成 ✓";
  } else if (diff <= 0){
    card.classList.add("today");
    s.className = "evstate today";
    s.textContent = "就是今天";
  } else {
    s.className = "evstate pending";
    s.textContent = "还没到 · 还有 " + diff + " 天";
  }
  card.appendChild(d);
  card.appendChild(t);
  card.appendChild(s);
  if (!done){
    const b = document.createElement("button");
    b.type = "button";
    b.className = "evknow";
    b.textContent = "知道了";
    b.addEventListener("click", function (){
      evSetDone(ev.id);
      loadMem();
    });
    card.appendChild(b);
  }
  return card;
}
function renderEventCards(list, items){
  const evs = [];
  items.forEach(function(it){
    const txt = String(it.text || "");
    if (!EV_WORDS.some(function(w){ return txt.indexOf(w) >= 0; })) return;
    const d = evParseDate(txt) || bjTodayStart();
    evs.push({ id: Number(it.id || 0), text: txt, date: d });
  });
  if (!evs.length) return;
  const wrap = document.createElement("div");
  wrap.className = "evwrap";
  const t0 = bjTodayStart();
  evs.slice(0, 3).forEach(function(ev){ wrap.appendChild(evCard(ev, t0)); });
  if (evs.length > 3){
    const extra = evs.slice(3);
    const fold = document.createElement("button");
    fold.type = "button";
    fold.className = "evfold";
    fold.textContent = "还有 " + extra.length + " 件";
    const box = document.createElement("div");
    box.hidden = true;
    extra.forEach(function(ev){ box.appendChild(evCard(ev, t0)); });
    fold.addEventListener("click", function (){
      box.hidden = !box.hidden;
      fold.textContent = box.hidden ? ("还有 " + extra.length + " 件") : "收起";
    });
    wrap.appendChild(fold);
    wrap.appendChild(box);
  }
  list.appendChild(wrap);
}

/* ══════════ 三期演示模式（T6-T10）：剧本 + 播放器 + 特效 ══════════ */
var DEMO_SCRIPT = [
  { t:"user", text:"我下周三回来看你", wait: 600 },
  { t:"ai",   text:"下周三啊，我记下了。要不要我到那天提醒您？", wait: 1200 },
  { t:"fx",   fx:"memoryAdd", wait: 800,
    data:{ text:"我下周三回来看你", group:"今天" } },
  { t:"fx",   fx:"eventCard", wait: 800,
    data:{ date:"12月2日 周三", text:"女儿回来看我", state:"pending" } },
  { t:"user", text:"我血压高，每天要吃降压药", wait: 600 },
  { t:"ai",   text:"这个我记着。药别断。", wait: 1000 },
  { t:"fx",   fx:"memoryAdd", wait: 400, data:{ text:"我血压高，每天要吃降压药", group:"今天" } },
  { t:"fx",   fx:"memoryAdd", wait: 400, data:{ text:"我爱吃软的，不吃辣", group:"今天" } },
  { t:"user", text:"我上次说的那个药是什么", wait: 600 },
  { t:"ai",   text:"这个您没跟我说过。", wait: 2000 },
  { t:"fx",   fx:"proactive", wait: 1500,
    data:{ text:"您女儿下周三回来，要不要提前收拾一下？" } },
  { t:"user", text:"我明天八点去医院", wait: 600 },
  { t:"ai",   text:"明天八点，我记下了。", wait: 1000 },
  { t:"fx",   fx:"reminderCard", wait: 1200,
    data:{ title:"明天八点去医院", at:"08:00" } },
  { t:"fx",   fx:"ringSoon", wait: 1200 },
  { t:"fx",   fx:"ringDue",  wait: 1200 },
  { t:"fx",   fx:"ackReminder", wait: 800 },
  { t:"fx",   fx:"elderMode", wait: 1600 },
  { t:"fx",   fx:"style", wait: 1400, data:{ name:"sakura" } },
  { t:"fx",   fx:"style", wait: 1400, data:{ name:"paper" } },
  { t:"fx",   fx:"recap", wait: 1600 },
  { t:"fx",   fx:"family", wait: 2000 },
  { t:"fx",   fx:"free", wait: 1600 }
];

function demoStart(){
  demoCapInit();
  if (DEMO.on && DEMO.idx > 0) return;
  DEMO.on = true;
  DEMO.idx = 0;
  DEMO.paused = false;
  DEMO.savedElder = document.body.getAttribute("data-elder") || "0";
  DEMO.savedFont = document.body.style.getPropertyValue("--fs") || "1";
  DEMO.savedStyle = document.documentElement.dataset.style || "";
  document.body.classList.add("demoing");
  said.textContent = "";
  $("demobar").hidden = false;
  $("demoPause").textContent = "暂停";
  demoStep();
}

function demoExit(){
  try { demoLiveReset(); } catch(e){}
  if (!DEMO.on) return;
  DEMO.on = false;
  DEMO.paused = false;
  clearTimeout(DEMO.timer);
  DEMO.timer = 0;
  ["demo_state","demo_mem","demo_rem"].forEach(function(k){
    try { localStorage.removeItem(k); } catch(e){}
    try { localStorage.removeItem("xiaonuan." + k); } catch(e){}
  });
  document.body.classList.remove("demoing");
  document.body.setAttribute("data-elder", DEMO.savedElder);
  document.body.style.setProperty("--fs", DEMO.savedFont);
  if (DEMO.savedStyle) lsSet("style", DEMO.savedStyle);
  else { try { localStorage.removeItem("xiaonuan.style"); } catch(e){} }
  setStyle(DEMO.savedStyle || "paper", false);
  clearTimeout(DEMO.memT);
  DEMO.memT = 0;
  window.scrollTo(0, 0);
  const m = $("mid");
  if (m) m.scrollTop = 0;
  const cap = $("demoCap"); if (cap) cap.hidden = true;
  location.href = location.pathname;
}

function demoStep(){
  if (!DEMO.on) return;
  if (DEMO.free) return;
  if (typeof DEMO_SCRIPT === "undefined" || !DEMO_SCRIPT || !DEMO_SCRIPT.length) return;
  if (DEMO.idx >= DEMO_SCRIPT.length){ demoFinish(); return; }
  const step = DEMO_SCRIPT[DEMO.idx];
  demoRun(step);
  DEMO.idx += 1;
  DEMO.timer = setTimeout(function(){
    if (!DEMO.on) return;
    if (!DEMO.paused) demoStep();
    else demoWaitResume();
  }, step.wait || 800);
}
function demoWaitResume(){
  DEMO.timer = setTimeout(function(){
    if (!DEMO.on) return;
    if (DEMO.paused) demoWaitResume();
    else demoStep();
  }, 200);
}
function demoPauseToggle(){
  if (!DEMO.on) return;
  DEMO.paused = !DEMO.paused;
  $("demoPause").textContent = DEMO.paused ? "继续" : "暂停";
}
function demoSkip(){
  if (!DEMO.on) return;
  clearTimeout(DEMO.timer);
  demoStep();
}
function demoFinish(){
  clearTimeout(DEMO.timer);
  DEMO.timer = 0;
}

var DEMO_CAPS = [
  "她记住了一件事",              // 1 user
  "她回了一句，也没有多问",       // 2 ai
  "这一条进了她的记忆",           // 3 memoryAdd
  "又说了一件",                   // 4 user
  "她记着",                       // 5 ai
  "记忆里有两条了",               // 6 memoryAdd
  "再一件",                       // 7 user
  "三条",                         // 8 memoryAdd
  "问一件她没听过的事",           // 9 user
  "她不会编",                     // 10 ai
  "这次是她先开口",               // 11 proactive
  "说个时间",                     // 12 user
  "她记下了",                     // 13 ai
  "明天八点，提醒生成",           // 14 reminderCard
  "出门前一小时",                 // 15 ringSoon
  "到点了",                       // 16 ringDue
  "回一句，她就知道办完了",       // 17 ackReminder
  "字大一点",                     // 18 elderMode
  "换个外观也可以",                // 19 style sakura
  "回到纸墨",                     // 20 style paper
  "今天，她记住了这些",            // 21 recap
  "她记得"                        // 22 end
];

function demoCapInit(){
  if (typeof DEMO_CAPS === "undefined" || !DEMO_CAPS || !DEMO_CAPS.length) return;
  const dots = $("demoCapDots");
  if (!dots) return;
  dots.innerHTML = "";
  for (let i = 0; i < DEMO_CAPS.length; i++){
    const d = document.createElement("i");
    dots.appendChild(d);
  }
  const bar = $("demoCap");
  if (bar) bar.hidden = false;
}

function demoCapSet(i){
  if (typeof DEMO_CAPS === "undefined" || !DEMO_CAPS) return;
  const txt = $("demoCapTxt");
  const dots = $("demoCapDots");
  if (txt){
    txt.textContent = DEMO_CAPS[i] || "";
    txt.style.animation = "none";
    void txt.offsetWidth;
    txt.style.animation = "";
  }
  if (dots){
    Array.prototype.forEach.call(dots.children, function(el, k){
      el.className = k === i ? "on" : "";
    });
  }
}

function demoRun(step){
  demoCapSet(DEMO.idx);

  if (step.t === "user") return demoBubble("user", step.text);
  if (step.t === "ai")   return demoBubble("ai", step.text);
  if (step.t === "fx")   return demoFx(step.fx, step.data || {});
}
function demoScroll(){
  const box = said.parentElement;
  if (box) box.scrollTop = box.scrollHeight;
}
function demoBubble(role, text){
  if (role === "ai"){
    const tp = document.createElement("div");
    tp.className = "demoTyping";
    tp.innerHTML = "<i></i><i></i><i></i>";
    said.appendChild(tp);
    demoScroll();
    setTimeout(function(){
      if (tp.parentNode) tp.parentNode.removeChild(tp);
      demoBubbleNow("ai", text);
    }, Math.min(900, Math.max(450, text.length * 22)));
    return;
  }
  demoBubbleNow(role, text);
}

function demoBubbleNow(role, text){
  const row = document.createElement("div");
  row.className = "drow " + role;
  const b = document.createElement("div");
  b.className = "dbubble";
  b.textContent = text;
  row.appendChild(b);
  said.appendChild(row);
  demoScroll();
}

function demoFx(name, data){
  switch(name){
    case "memoryAdd":    return demoMemoryAdd(data);
    case "eventCard":    return demoEventCard(data);
    case "proactive":    demoBubble("pro", data.text); demoBump("tbPro"); return;
    case "reminderCard": return demoReminder(data);
    case "ringSoon":     return demoRing("soon");
    case "ringDue":      return demoRing("due");
    case "ackReminder":  return demoAck();
    case "elderMode":    return demoElder();
    case "style":        return demoStyle(data);
    case "recap":        return demoRecap();
    case "free":         return demoEnterFree();
    case "family":       return demoFamily();
    case "end":          return demoEnd();
  }
}

function demoMemoryAdd(data){
  openMem();
  const list = $("memlist");
  if (!list) return;
  let tl = list.querySelector(".memtl");
  if (!tl){
    tl = document.createElement("div");
    tl.className = "memtl";
    list.appendChild(tl);
  }
  let group = tl.querySelector('.tlgroup[data-k="' + data.group + '"]');
  if (!group){
    group = document.createElement("div");
    group.className = "tlgroup";
    group.dataset.k = data.group;
    const h = document.createElement("div");
    h.className = "tlhead";
    h.textContent = data.group;
    group.appendChild(h);
    tl.appendChild(group);
  }
  const item = document.createElement("div");
  item.className = "tlitem";
  const dot = document.createElement("span");
  dot.className = "tldot";
  const body = document.createElement("div");
  body.className = "tlbody";
  const tx = document.createElement("div");
  tx.className = "tltext";
  tx.textContent = data.text;
  const mt = document.createElement("div");
  mt.className = "tlmeta";
  mt.textContent = "说过 1 次 · 刚刚";
  body.appendChild(tx); body.appendChild(mt);
  item.appendChild(dot); item.appendChild(body);
  group.appendChild(item);
  demoBump("tbMem");
  /* 四期：抽屉开 1.6s 后自动关，不挡对话 */
  clearTimeout(DEMO.memT);
  DEMO.memT = setTimeout(closeMem, 1600);
}

function demoEventCard(data){
  openMem();
  const list = $("memlist");
  if (!list) return;
  let card = list.querySelector(".evcard");
  if (!card){
    card = document.createElement("div");
    card.className = "evcard";
    list.insertBefore(card, list.firstChild);
  }
  card.innerHTML = "";
  const d = document.createElement("div"); d.className = "evdate"; d.textContent = data.date;
  const t = document.createElement("div"); t.className = "evtext"; t.textContent = data.text;
  const s = document.createElement("div"); s.className = "evstate pending"; s.textContent = "还没到";
  card.appendChild(d); card.appendChild(t); card.appendChild(s);
}

function demoReminder(data){
  closeMem();
  const wrap = $("cardwrap");
  if (!wrap) return;
  $("ct").textContent = "明天有件事";
  $("ctime").textContent = data.at;
  $("cw").textContent = data.title;
  wrap.hidden = false;
  demoBump("tbRem");
  demoRing("day");
}

function demoRing(state){
  const fg = document.querySelector("#cardwrap .ring-fg");
  if (!fg) return;
  const C = RING_C;
  fg.classList.remove("soon", "due");
  const txt = document.querySelector("#cardwrap .ringtxt");
  if (state === "day"){
    fg.setAttribute("stroke-dashoffset", String(C * 0.05));
    if (txt) txt.textContent = "24h";
  }
  if (state === "soon"){
    fg.setAttribute("stroke-dashoffset", String(C * 0.62));
    fg.classList.add("soon");
    if (txt) txt.textContent = "1h";
  }
  if (state === "due"){
    fg.setAttribute("stroke-dashoffset", String(C));
    fg.classList.add("due");
    if (txt) txt.textContent = "到点";
  }
}

function demoAck(){
  $("cardwrap").hidden = true;
  openMem();
  const card = document.querySelector("#memlist .evcard");
  if (card){
    card.classList.add("done");
    const s = card.querySelector(".evstate");
    if (s){ s.className = "evstate done"; s.textContent = "已完成 ✓"; }
  }
}

function demoStyle(data){
  if (window.setStyle) setStyle(data.name);
  demoPulseAll();
}

function demoRecap(){
  const said = $("said");
  if (!said) return;
  const box = document.createElement("div");
  box.className = "drecap";
  box.innerHTML = "<span>今天记住 3 条</span><span>提醒 1 次</span><span>主动开口 1 次</span>";
  said.appendChild(box);
  demoScroll();
}

function demoPulseAll(){
  ["tbMem","tbRem","tbPro","todaybar"].forEach(function(id){
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("demoPulse");
    void el.offsetWidth;
    el.classList.add("demoPulse");
  });
}

function demoElder(){
  closeMem();
  document.body.setAttribute("data-elder", "1");
  document.body.style.setProperty("--fs", "1.15");
}

function demoEnd(){
  const box = document.createElement("div");
  box.className = "demoend";
  box.innerHTML = "<div>她记得</div><div>她不编</div><div>她先开口</div>" +
                  "<p>演示结束，点「退出演示」回到真实数据</p>";
  said.appendChild(box);
  demoScroll();
}

function demoBump(id){
  const el0 = document.getElementById(id);
  if (el0){ el0.classList.remove("demoPulse"); void el0.offsetWidth; el0.classList.add("demoPulse"); }
  const el = $(id);
  if (!el) return;
  el.textContent = String(Number(el.textContent || 0) + 1);
  el.classList.remove("pop");
  void el.offsetWidth;
  el.classList.add("pop");
}

$("mDemo").addEventListener("click", function(){
  $("sheetbg").hidden = true;
  openIntro();
});
$("demoPause").addEventListener("click", demoPauseToggle);
$("demoSkip").addEventListener("click", demoSkip);
$("demoExitBtn").addEventListener("click", demoExit);
document.addEventListener("keydown", function(e){
  if (e.key === "Escape" && DEMO.on){ demoExit(); return; }
  if (e.ctrlKey && e.shiftKey && (e.key === "D" || e.key === "d")){
    e.preventDefault();
    if (DEMO.on) demoExit(); else demoStart();
  }
  if (DEMO.on && e.key === " "){ e.preventDefault(); demoSkip(); }
});

if (DEMO.on) setTimeout(demoStart, 400);

updateTodayBar();

/* ===== */

(function(){
  function show(){
    try{
      var id = localStorage.getItem("uid") || "";
      var el = document.getElementById("guestline");
      if (el) el.hidden = (id.indexOf("g_") !== 0);
    }catch(e){}
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", show);
  else show();
  window.addEventListener("load", show);
})();

/* ===== */

/* 五期：?demo=1&selftest=1 演示自检。只观察 DOM，不改 19 步脚本 */
(function(){
  const q = location.search;
  if (!/[?&]demo=1(?:&|$)/.test(q) || !/[?&]selftest=1(?:&|$)/.test(q)) return;

  const STEPS = [
    { name:"用户气泡 1", sel:".drow.user", min:1 },
    { name:"小暖回复 1", sel:".drow.ai", min:1 },
    { name:"记忆入轴 1", sel:"#memlist .tlitem", min:1 },
    { name:"事件卡", sel:"#memlist .evcard", min:1 },
    { name:"用户气泡 2", sel:".drow.user", min:2 },
    { name:"小暖回复 2", sel:".drow.ai", min:2 },
    { name:"记忆入轴 2", sel:"#memlist .tlitem", min:2 },
    { name:"记忆入轴 3", sel:"#memlist .tlitem", min:3 },
    { name:"用户气泡 3", sel:".drow.user", min:3 },
    { name:"小暖回复 3", sel:".drow.ai", min:3 },
    { name:"主动开口", sel:".drow.pro", min:1 },
    { name:"用户气泡 4", sel:".drow.user", min:4 },
    { name:"小暖回复 4", sel:".drow.ai", min:4 },
    { name:"提醒卡", check:function(){
        const w = document.getElementById("cardwrap");
        const cw = document.getElementById("cw");
        return !!w && !w.hidden && !!cw && cw.textContent.length > 0;
      } },
    { name:"环·将到", sel:"#cardwrap .ring-fg.soon" },
    { name:"环·到点", sel:"#cardwrap .ring-fg.due" },
    { name:"回执完成", sel:"#memlist .evcard.done" },
    { name:"老人模式", sel:'body[data-elder="1"]' },
    { name:"收尾字幕", sel:"#said .demoend" }
  ];
  const TOTAL = STEPS.length;
  const marks = STEPS.map(function(){ return false; });

  const box = document.createElement("div");
  box.id = "selftestOut";
  box.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#111820;color:#EDEDED;" +
    "font:12px/1.6 Consolas,monospace;padding:10px 12px;border-top:2px solid #3B6FE0;" +
    "max-height:44vh;overflow:auto;white-space:pre-wrap";
  const msgEl = document.createElement("div");
  msgEl.id = "selftestMsg";
  msgEl.style.cssText = "font-weight:700;font-size:13px;margin-bottom:2px";
  const apiEl = document.createElement("div");
  apiEl.id = "selftestApi";
  const stepEl = document.createElement("div");
  stepEl.id = "selftestSteps";
  stepEl.style.cssText = "opacity:.85;margin-top:4px";
  box.appendChild(msgEl); box.appendChild(apiEl); box.appendChild(stepEl);
  document.body.appendChild(box);
  msgEl.textContent = "演示自检运行中…";

  function count(sel){ try { return document.querySelectorAll(sel).length; } catch(e){ return 0; } }
  function apiCount(){ return (window.__xnApi || []).length; }

  let fired = false;
  let timer = 0;

  function paint(){
    stepEl.textContent = "步骤：" + STEPS.map(function(s, i){
      return (marks[i] ? "✓" : "·") + String(i + 1).padStart(2, "0");
    }).join(" ");
    apiEl.textContent = "API 请求：" + apiCount() + " 次（断言 0）";
  }

  function finish(){
    fired = true;
    clearInterval(timer);
    const fails = [];
    STEPS.forEach(function(s, i){
      if (!marks[i]) fails.push("第" + String(i + 1).padStart(2, "0") + "步 " + s.name);
    });
    const pass = TOTAL - fails.length;
    const api = apiCount();
    msgEl.textContent = "演示自检 通过 " + pass + "/" + TOTAL + "，失败项：" + (fails.length ? fails.join("、") : "无") +
      " ｜ API 请求 " + api + " 次（断言 0）" + (api === 0 ? " 通过" : " 失败");
    stepEl.textContent = "全部步骤：" + STEPS.map(function(s, i){ return (i + 1) + (marks[i] ? "✓" : "✗"); }).join(" ") +
      (fails.length ? "　失败：" + fails.join("；") : "");
    box.dataset.done = "1";
    box.dataset.pass = String(pass);
    box.dataset.api = String(api);
    window.__selftest = { pass: pass, total: TOTAL, fail: fails, api: api, done: true };
    document.title = "SELFTEST " + pass + "/" + TOTAL + " API " + api;
  }

  timer = setInterval(function(){
    if (fired) return;
    const reached = (typeof DEMO !== "undefined" && DEMO) ? DEMO.idx : 0;
    for (let i = 0; i < TOTAL; i++){
      if (marks[i] || i >= reached) continue;
      const s = STEPS[i];
      if (s.check ? s.check() : count(s.sel) >= (s.min || 1)) marks[i] = true;
    }
    paint();
    if (reached >= TOTAL) finish();
  }, 80);
})();
