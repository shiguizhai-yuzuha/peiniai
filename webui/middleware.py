"""关防 · 中间件：把 / 换成新界面。

负责
  · GET / 直接返回 static/app/index.html
  · /?ui=old 走 Gradio 旧界面
  · /logout 302 改写到 /app

不负责
  · 不改任何业务逻辑"""
# 名字　关防 —— 守卫的制度，不是门神。制度不靠年画。


import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RootSwitch:
    """让 / 变成新界面，旧界面挪到 /old

    只改路径，不改 Gradio 的任何东西：
        GET /        → 302 到 /app
        GET /old/**  → 内部改写成 /**，交给 Gradio
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # WebSocket 也要改写路径，否则旧界面的按钮全都没反应
        if scope.get("type") == "websocket":
            wp = scope.get("path", "/")
            if wp == "/old" or wp.startswith("/old/"):
                scope = dict(scope)
                scope["path"] = wp[4:] or "/"
                raw = scope.get("raw_path")
                if raw:
                    scope["raw_path"] = raw[4:] or b"/"
            await self.app(scope, receive, send)
            return

        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        hdrs = dict(scope.get("headers") or [])
        referer = (hdrs.get(b"referer") or b"").decode("latin-1", "ignore")

        # 从旧界面点出去的（登出、返回首页），送他回 /old，别丢到新界面
        came_from_old = "/old" in referer
        target_root = "/old" if came_from_old else "/app"

        qs = scope.get("query_string", b"").decode("latin-1")

        if path == "/":
            # 由参数决定渲染哪一套，不做跳转。
            #   /            渲染新界面（默认）
            #   /?ui=old     渲染旧界面（交给 Gradio）
            #   /?ui=new     渲染新界面
            # 另外兼容以前的 ?old=1
            want_old = ("ui=old" in qs) or ("old=1" in qs)
            want_new = "ui=new" in qs

            # 旧界面里的页面自己跳回 "/" 时不带参数 → 看 referer 兜住
            if not want_old and not want_new and "ui=old" in referer:
                want_old = True

            if want_old:
                # Gradio 就在 "/" 上，直接放行，它渲染旧界面
                await self.app(scope, receive, send)
                return

            # 新界面：直接把 HTML 返回，状态 200，URL 保持 "/"
            try:
                from starlette.responses import Response
                base = _ROOT
                fp = os.path.join(base, "static", "app", "index.html")
                with open(fp, "rb") as f:
                    body = f.read()
                await Response(body, media_type="text/html; charset=utf-8")(
                    scope, receive, send)
                return
            except Exception:
                from starlette.responses import RedirectResponse
                await RedirectResponse("/app", status_code=302)(scope, receive, send)
                return

        # 旧的 /old 入口 → 直接跳到 Gradio 的根路径
        if path in ("/old", "/old/"):
            from starlette.responses import RedirectResponse
            await RedirectResponse("/?ui=old", status_code=302)(scope, receive, send)
            return

        # Gradio 登出后会 302 到 "/"，把它改成 /old
        if path in ("/logout", "/logout/"):
            async def _send(message):
                if message.get("type") == "http.response.start":
                    hh = [(k, v) for k, v in message.get("headers", [])
                          if k.lower() != b"location"]
                    hh.append((b"location", b"/?old=1" if "old=1" in referer else b"/app"))
                    message = dict(message)
                    message["headers"] = hh
                await send(message)
            await self.app(scope, receive, _send)
            return

        # 旧界面必须带斜杠，否则 <base href="./"> 会解析成 "/"，
        # 浏览器地址和资源路径对不上，页面里的跳转就乱了
        if path == "/old":
            from starlette.responses import RedirectResponse
            q = scope.get("query_string", b"").decode("latin-1")
            await RedirectResponse("/old/" + (("?" + q) if q else ""),
                                   status_code=302)(scope, receive, send)
            return

        if path == "/old" or path.startswith("/old/"):
            scope = dict(scope)
            scope["path"] = path[4:] or "/"
            raw = scope.get("raw_path")
            if raw:
                scope["raw_path"] = raw[4:] or b"/"

        await self.app(scope, receive, send)
