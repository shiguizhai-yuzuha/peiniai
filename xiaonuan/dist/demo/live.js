/* 小暖 · 演示 v2：真实调用（只管请求与计时） */

window.XNDemoLive = (function () {
  const CO = window.XNDemoScript.COPY;

  function uid() {
    try {
      let id = localStorage.getItem("uid") || "";
      if (!id) {
        id = "g_" + (window.crypto && crypto.randomUUID
          ? crypto.randomUUID().replace(/-/g, "")
          : Date.now().toString(36));
        localStorage.setItem("uid", id);
      }
      return id;
    } catch (e) {
      return "judge";
    }
  }

  async function send(text) {
    const body = JSON.stringify({ text: String(text || "").slice(0, 500), uid: uid() });
    const t0 = performance.now();
    let resp;
    try {
      resp = await fetch(window.XN_API + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body
      });
    } catch (e) {
      return { ok: false, kind: "network", ms: Math.round(performance.now() - t0), error: String(e && e.message || e) };
    }
    const ms = Math.round(performance.now() - t0);
    const raw = await resp.text();
    let data = null;
    try { data = JSON.parse(raw); } catch (e) { data = null; }
    if (!data) {
      return { ok: false, kind: "not_json", status: resp.status, ms: ms, error: raw.slice(0, 120) };
    }
    if (!data.ok) {
      return { ok: false, kind: "api", status: resp.status, ms: ms, error: data.error || "failed" };
    }
    return {
      ok: true,
      ms: data.ms || ms,
      reply: String(data.reply || "").trim(),
      memories: data.memories || []
    };
  }

  async function memories() {
    try {
      const r = await fetch(window.XN_API + "/memories?uid=" + encodeURIComponent(uid()), { cache: "no-store" });
      const d = await r.json();
      return (d && d.items) || [];
    } catch (e) {
      return [];
    }
  }

  return { send: send, memories: memories, uid: uid, copy: CO };
})();
