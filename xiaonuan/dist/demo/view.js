/* 小暖 · 演示 v2：画面（只画，不管流程） */

window.XNDemoView = (function () {
  const S = window.XNDemoScript;
  const T = S.TIMING;
  const CO = S.COPY;

  const $ = function (id) { return document.getElementById(id); };
  const said = function () { return $("said"); };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function scroll() {
    const box = $("said");
    const holder = box && box.parentElement;
    if (holder) holder.scrollTop = holder.scrollHeight;
  }

  // ── 控件 ──
  function buildBar() {
    const bar = document.querySelector(".demobar");
    if (!bar || bar.dataset.rebuilt === "1") return;
    bar.dataset.rebuilt = "1";
    bar.innerHTML = "";
    bar.appendChild(el("span", "demobar-txt", CO.bar));

    const btns = el("span", "demobar-btns");
    [["demoNext", CO.next], ["demoPause", CO.pause], ["demoLiveBtn", CO.live],
     ["demoSkip", CO.skip], ["demoExitBtn", CO.exit]].forEach(function (b) {
      const x = el("button", null, b[1]);
      x.id = b[0];
      x.type = "button";
      btns.appendChild(x);
    });
    bar.appendChild(btns);
  }

  function setPauseLabel(paused) {
    const b = $("demoPause");
    if (b) b.textContent = paused ? CO.resume : CO.pause;
  }

  // ── 气泡 ──
  function bubble(role, text, withTyping) {
    const host = said();
    if (!host) return;

    if (withTyping) {
      const tp = el("div", "demoTyping");
      tp.innerHTML = "<i></i><i></i><i></i>";
      host.appendChild(tp);
      scroll();
      setTimeout(function () {
        if (tp.parentNode) tp.parentNode.removeChild(tp);
        bubbleNow(role, text);
      }, Math.min(900, Math.max(380, (text || "").length * 20)));
      return;
    }
    bubbleNow(role, text);
  }

  function bubbleNow(role, text) {
    const host = said();
    if (!host) return;
    const row = el("div", "drow " + role);
    row.appendChild(el("div", "dbubble", text));
    host.appendChild(row);
    scroll();
  }

  // ── 字幕与进度 ──
  function caption(text, idx, total) {
    const t = $("demoCapTxt");
    if (t) {
      t.textContent = text || "";
      t.style.animation = "none";
      void t.offsetWidth;
      t.style.animation = "";
    }
    const dots = $("demoCapDots");
    if (dots && dots.children.length !== total) {
      dots.innerHTML = "";
      for (let i = 0; i < total; i++) dots.appendChild(el("i"));
    }
    if (dots) {
      Array.prototype.forEach.call(dots.children, function (d, i) {
        d.className = i === idx ? "on" : "";
      });
    }
  }

  function pulse(id) {
    const e = $(id);
    if (!e) return;
    e.classList.remove("demoPulse");
    void e.offsetWidth;
    e.classList.add("demoPulse");
  }

  function bump(id) {
    const e = $(id);
    if (!e) return;
    e.textContent = String(Number(e.textContent || 0) + 1);
    pulse(id);
  }

  // ── 记忆 / 事件卡 / 提醒 ──
  function memory(data) {
    const list = $("memlist");
    if (!list) return;
    let tl = list.querySelector(".memtl");
    if (!tl) { tl = el("div", "memtl"); list.appendChild(tl); }
    let group = tl.querySelector('.tlgroup[data-k="今天"]');
    if (!group) {
      group = el("div", "tlgroup");
      group.dataset.k = "今天";
      group.appendChild(el("div", "tlhead", "今天"));
      tl.appendChild(group);
    }
    const item = el("div", "tlitem");
    item.appendChild(el("span", "tldot"));
    const body = el("div", "tlbody");
    body.appendChild(el("div", "tltext", data.text));
    body.appendChild(el("div", "tlmeta", "说过 1 次 · 刚刚"));
    item.appendChild(body);
    group.appendChild(item);
    bump("tbMem");
  }

  function eventCard(data) {
    const list = $("memlist");
    if (!list) return;
    let card = list.querySelector(".evcard");
    if (!card) { card = el("div", "evcard"); list.insertBefore(card, list.firstChild); }
    card.innerHTML = "";
    card.appendChild(el("div", "evdate", data.date));
    card.appendChild(el("div", "evtext", data.text));
    card.appendChild(el("div", "evstate pending", "还没到"));
    card.dataset.state = "pending";
  }

  function reminder(data) {
    const wrap = $("cardwrap");
    if (!wrap) return;
    wrap.hidden = false;
    if ($("ct")) $("ct").textContent = "明天有件事";
    if ($("ctime")) $("ctime").textContent = data.at;
    if ($("cw")) $("cw").textContent = data.title;
    ring("day");
  }

  function ring(stage) {
    const fg = document.querySelector(".ring .ring-fg");
    if (!fg) return;
    const C = 113;
    fg.classList.remove("soon", "due");
    if (stage === "day") fg.style.strokeDashoffset = String(C * 0.05);
    if (stage === "soon") { fg.style.strokeDashoffset = String(C * 0.62); fg.classList.add("soon"); }
    if (stage === "due") { fg.style.strokeDashoffset = String(C); fg.classList.add("due"); }
  }

  function ack() {
    const wrap = $("cardwrap");
    if (wrap) wrap.hidden = true;
    const card = document.querySelector(".evcard");
    if (!card) return;
    card.dataset.state = "done";
    const s = card.querySelector(".evstate");
    if (s) { s.className = "evstate done"; s.textContent = "已完成"; }
  }

  function elder() {
    document.documentElement.dataset.elder = "1";
    pulse("todaybar");
  }

  function style(name) {
    if (window.setStyle) window.setStyle(name);
  }

  function facts(snap) {
    const ov = $("factsOv"), box = $("factsList");
    if (!ov || !box) return;

    const fallback = [
      ["人物", ["小敏 · 女儿 · 在上海"]],
      ["事件", ["去医院复查血压 · 下周三"]],
      ["计划", ["下周三打三角洲"]],
      ["身体", ["血压偏高"]],
      ["承诺", ["明天八点提醒去医院（小暖）"]]
    ];

    function render(rows) {
      box.innerHTML = rows.map(function (r) {
        return '<div class="frow"><b>' + r[0] + '</b><span>' +
          r[1].map(function (x) { return '<i>' + x + '</i>'; }).join("") + '</span></div>';
      }).join("");
    }
    render(fallback);
    ov.hidden = false;
    clearTimeout(facts._t);
    facts._t = setTimeout(function () { ov.hidden = true; }, 5200);

    // 真实抽取结果优先
    const uid = (function () {
      try { return localStorage.getItem("uid") || "judge"; } catch (e) { return "judge"; }
    })();
    fetch((window.XN_API || "https://peiniai.cn/xn") + "/facts?uid=" + encodeURIComponent(uid),
          { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        const kinds = (d && d.kinds) || {};
        const label = { name: "名字", people: "人物", events: "事件", plans: "计划",
                        health: "身体", likes: "喜欢", dislikes: "不喜欢", promises: "承诺" };
        const rows = [];
        Object.keys(label).forEach(function (k) {
          const arr = (kinds[k] || []).slice(0, 3).map(function (x) { return x.val || x; });
          if (arr.length) rows.push([label[k], arr]);
        });
        if (rows.length) render(rows);
      })
      .catch(function () {});
  }

  function family(snap) {
    const fo = $("factsOv");
    if (fo) fo.hidden = true;
    const ov = $("famOv"), rows = $("famRows");
    if (!ov || !rows) return;

    // 先用本地数据占位，立刻可见
    const items = [].slice.call(document.querySelectorAll(".tltext")).map(function (e) {
      return e.textContent.trim();
    }).filter(Boolean);
    rows.innerHTML = [
      ["今天记住", (items.length || 3) + " 件事"],
      ["提醒", "1 次（明天 08:00 去医院）"],
      ["主动开口", "1 次（收拾房间）"],
      ["情绪", "平稳"]
    ].map(function (r) {
      return '<div class="famrow"><b>' + r[0] + '</b><span>' + r[1] + '</span></div>';
    }).join("");
    ov.hidden = false;
    clearTimeout(family._t);
    family._t = setTimeout(function () { ov.hidden = true; }, T.familyHold);

    // 再用 pandas 结果替换（真统计）
    const uid = (window.XNDemoLive && window.XNDemoLive.uid) ? window.XNDemoLive.uid() : "judge";
    fetch(window.XN_API + "/family?uid=" + encodeURIComponent(uid), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) return;
        rows.innerHTML = (d.rows || []).map(function (r) {
          return '<div class="famrow"><b>' + r.k + '</b><span>' + r.v + '</span></div>';
        }).join("");

        const box = $("famChart");
        if (box && d.chart && d.chart.length) {
          const max = Math.max.apply(null, d.chart.map(function (c) { return c.n; })) || 1;
          box.innerHTML = d.chart.map(function (c) {
            const h = Math.max(6, Math.round(c.n / max * 100));
            return '<div class="bar"><i style="height:' + h + '%"></i><span>' + c.d.slice(3) + '</span></div>';
          }).join("");
        }
        const tag = $("famLib");
        if (tag) {
          tag.textContent = (d.lib || "pandas") + " · " + d.elapsed_ms + " ms";
          tag.hidden = false;
        }
        // 延长展示，让评委看清
        clearTimeout(family._t);
        family._t = setTimeout(function () { ov.hidden = true; }, T.familyHold + 1500);
      })
      .catch(function () {});
  }

  function live(snap) {
    const box = $("demoLive");
    if (box) box.hidden = false;
    const inp = $("demoLiveInp");
    if (inp) {
      inp.placeholder = CO.livePlaceholder;
      setTimeout(function () { inp.focus(); }, 80);
    }
    caption(S.STEPS[S.STEPS.length - 1].cap, S.STEPS.length - 1, S.STEPS.length);
    bubbleNow("ai", "现在轮到您。随便说一句，比如「我下周三要复查」。");
  }

  function clearAll() {
    const host = said();
    if (host) host.textContent = "";
    const box = $("demoLive");
    if (box) box.hidden = true;
    const fam = $("famOv");
    if (fam) fam.hidden = true;
    const cap = $("demoCap");
    if (cap) cap.hidden = true;
    const wrap = $("cardwrap");
    if (wrap) wrap.hidden = true;
    document.querySelectorAll(".demobar [data-xn]").forEach(function (e) { e.remove(); });
  }

  function mountBar(visible) {
    const bar = document.querySelector(".demobar");
    if (bar) bar.hidden = !visible;
    const cap = $("demoCap");
    if (cap) cap.hidden = !visible;
  }

  return {
    buildBar: buildBar, setPauseLabel: setPauseLabel,
    bubble: bubble, bubbleNow: bubbleNow,
    caption: caption, pulse: pulse, bump: bump,
    memory: memory, eventCard: eventCard, reminder: reminder,
    ring: ring, ack: ack, elder: elder, style: style,
    facts: facts, family: family, live: live,
    clearAll: clearAll, mountBar: mountBar, scroll: scroll
  };
})();
