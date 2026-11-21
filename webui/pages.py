"""册页 · 页面：不是 Gradio 的那些整页 HTML。

负责
  · /app /home /piano /keys /ab /notice
  · /scene/{key} 场景页与动作接口

不负责
  · 不装配 Gradio 界面（那是 ui.py）"""
# 名字　册页 —— 书画装裱的一种：一页一页，各自完整。


import html
import os

# 页面一律不缓存。改完立刻生效，用户不用硬刷。
_NOCACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache", "Expires": "0"}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _keys_page():
    """电子琴"""
    from fastapi.responses import HTMLResponse
    base = _ROOT
    path = os.path.join(base, "static", "keys", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>读不到：%s</h1>" % e, status_code=500)


def _notice_page():
    """更新公告 —— 读 static/notice/ 下最新的 txt"""
    import glob as _glob, html as _html
    from fastapi.responses import HTMLResponse

    base = _ROOT
    d = os.path.join(base, "static", "notice")
    files = sorted(_glob.glob(os.path.join(d, "*.txt")), reverse=True)
    if not files:
        return HTMLResponse("<h1>还没有公告</h1>", status_code=404)

    raw = open(files[0], encoding="utf-8").read()
    body = _html.escape(raw)
    body = body.replace("\n", "<br>")

    page = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        "<title>更新公告</title><style>"
        "body{background:linear-gradient(180deg,#141a28,#0a0d13);background-attachment:fixed;"
        "color:#f2ece4;font-family:'Songti SC','Noto Serif SC',-apple-system,sans-serif;"
        "line-height:2.0;padding:0 0 80px;margin:0}"
        "#top{position:sticky;top:0;display:flex;justify-content:space-between;align-items:center;"
        "padding:14px 18px;background:rgba(10,13,19,.85);backdrop-filter:blur(12px);"
        "border-bottom:1px solid rgba(255,255,255,.1);font-size:12px;letter-spacing:.2em;"
        "color:rgba(242,236,228,.6)}"
        "#top a{color:rgba(242,236,228,.6);text-decoration:none;padding:.5em 1em;"
        "border:1px solid rgba(255,255,255,.1);border-radius:99px;font-size:11px}"
        ".w{max-width:680px;margin:0 auto;padding:32px 20px}"
        "pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;"
        "font-size:14.5px;line-height:2.0;color:rgba(242,236,228,.86);margin:0}"
        "</style></head><body>"
        "<div id='top'><span>更新公告</span><a href='/app'>回去</a></div>"
        "<div class='w'><pre>" + body + "</pre></div></body></html>"
    )
    return HTMLResponse(page)


_UNIVERSAL_BACK = """
<div id="pnBack"><span>← 回去聊天</span></div>
<style>
#pnBack{
  position:fixed; left:14px; top:14px; z-index:100000;
  padding:.62em 1.15em; border-radius:100px; cursor:pointer;
  background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.18);
  color:rgba(240,244,255,.88); backdrop-filter:blur(12px);
  font-family:"Songti SC","Noto Serif SC",serif;
  font-size:12.5px; letter-spacing:.18em;
  transition:transform .14s ease, background .26s ease, border-color .26s ease;
  -webkit-tap-highlight-color:transparent;
}
#pnBack:hover{ background:rgba(255,255,255,.16); border-color:rgba(255,255,255,.36); }
#pnBack:active{ transform:scale(.96); }
@media (max-width:480px){ #pnBack{ left:10px; top:10px; font-size:11.5px; padding:.55em 1em; } }
</style>
<script>
document.getElementById("pnBack").addEventListener("click", function(){
  window.location.href = "/app";
});
</script>
"""


def _ab_page():
    """音色盲测"""
    from fastapi.responses import HTMLResponse
    base = _ROOT
    path = os.path.join(base, "static", "piano", "ab.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>读不到：%s</h1>" % e, status_code=500)


def _piano_page():
    """她弹给你听"""
    from fastapi.responses import HTMLResponse
    base = _ROOT
    path = os.path.join(base, "static", "piano", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>读不到：%s</h1>" % e, status_code=500)


def _home_page():
    """功能主页：个人页 / 记忆 / 背景 / 记忆模式 / 导出"""
    from fastapi.responses import HTMLResponse
    base = _ROOT
    path = os.path.join(base, "static", "home", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>主页文件读不到：%s</h1>" % e, status_code=500)


def _app_page():
    """自写前端。单文件，全部内联，不依赖 /static/ 路由。"""
    from fastapi.responses import HTMLResponse
    base = _ROOT
    path = os.path.join(base, "static", "app", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>前端文件读不到：%s</h1>" % e, status_code=500)


def _ds_page():
    """直连 DeepSeek 的应急入口（独立于陪伴聊天）。"""
    from fastapi.responses import HTMLResponse
    path = os.path.join(_ROOT, "static", "app", "ds.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>页面读不到：%s</h1>" % e, status_code=500)


def _menu_page():
    """全部功能：一页跳转。"""
    from fastapi.responses import HTMLResponse
    path = os.path.join(_ROOT, "static", "menu", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>页面文件读不到：%s</h1>" % e, status_code=500)


def _voice_page():
    """她说话的样子。设置页，全部内联，不依赖 /static/ 路由。"""
    from fastapi.responses import HTMLResponse
    path = os.path.join(_ROOT, "static", "voice", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read(), headers=_NOCACHE)
    except Exception as e:
        return HTMLResponse("<h1>页面文件读不到：%s</h1>" % e, status_code=500)


def _scene_page(key: str, u: str = "", p: str = ""):
    """把 static/<path>/index.html 吐出来，并把 user/persona 注入进去。"""
    from fastapi.responses import HTMLResponse
    from core import scenes

    sc = scenes.get(key)
    if not sc:
        return HTMLResponse("<h1>没有这个场景</h1>", status_code=404)

    base = _ROOT
    path = os.path.join(base, "static", sc["path"])
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        return HTMLResponse("<h1>场景文件读不到：%s</h1>" % e, status_code=500)

    boot = ("<script>window.__SCENE_CTX={key:%s,user:%s,persona:%s};</script>"
            % (repr(key), repr(u), repr(p)))
    html = html.replace("</head>", boot + "</head>", 1)

    # 适配层的 JS 直接内联进来。
    # 不能靠 <script src="scene.js"> ——Gradio 不挂 /static/ 这个路径，
    # 相对地址会落到 /scene/scene.js 变成 404。
    js_path = os.path.join(os.path.dirname(path), "scene.js")
    try:
        with open(js_path, encoding="utf-8") as f:
            js = f.read()
        html = html.replace(
            '<script src="scene.js"></script>',
            "<script>\n" + js + "\n</script>", 1)
    except Exception as e:
        print("[场景] 内联 scene.js 失败：%s" % e, flush=True)

    # 场景自带返回（scene.js）就不管；没有就注入一个，保证任何场景都能回聊天页
    if "scene.js" not in html or not os.path.exists(
            os.path.join(os.path.dirname(path), "scene.js")):
        html = html.replace("</body>", _UNIVERSAL_BACK + "</body>", 1)

    return HTMLResponse(html)


def _scene_act(payload: dict):
    """前端发来一个动作。返回数值变化和一句台词。"""
    from core import scene_runtime as _rt
    try:
        u = (payload.get("user") or "").strip()
        p = (payload.get("persona") or "").strip()
        key = (payload.get("key") or "beach").strip()
        action = (payload.get("action") or "").strip()
        if not u or not p or not action:
            return {"ok": False, "reason": "参数不全"}
        if action == "enter":
            return {"ok": True, "entrance": _rt.entrance(u, p, key)}
        return _rt.act(u, p, key, action)
    except Exception as e:
        print("[场景] 动作失败：%s" % e, flush=True)
        return {"ok": False, "reason": str(e)}
