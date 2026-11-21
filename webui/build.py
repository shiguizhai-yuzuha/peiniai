"""结 · 装配：把路由和中间件挂到 Gradio 的应用上。

负责
  · 挂 9 个页面路由
  · 挂 RootSwitch
  · 挂 5 个 JSON API
  · 挂 IP 拦截

不负责
  · 不定义页面内容"""
# 名字　结 —— 榫卯的结。零件各自存在，结一上，才是一座房。


import gradio.routes as _gr_routes

from core.ipblock import IPBlockMiddleware

from webui.middleware import RootSwitch
from webui.pages import (_ab_page, _app_page, _home_page, _keys_page, _notice_page, _ds_page,
                        _piano_page, _scene_act, _scene_page, _voice_page, _menu_page)
from webui.routes import _bg_image, _keepsake_dl, _keepsake_file
from webui.story import _story_page

# 抓住 Gradio 原来的 create_app。
# 必须在替换之前抓住——这就是"包一层"的前提。
# 放在本模块里而不是 app.py 里，是为了让这个模块自己能独立成立。
_orig_create_app = _gr_routes.App.create_app


def _create_app_with_ipblock(*args, **kwargs):
    _app = _orig_create_app(*args, **kwargs)
    try:
        _app.add_api_route("/story/{sid}", _story_page, methods=["GET"])
        _app.add_api_route("/keepsake/dl/{name}", _keepsake_dl, methods=["GET"])
        _app.add_api_route("/keepsake/{name}", _keepsake_file, methods=["GET"])
        _app.add_api_route("/scene/{key}", _scene_page, methods=["GET"])
        def _app_asset(name: str):
            from fastapi.responses import FileResponse, JSONResponse
            import os as _os
            base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                 "static", "app")
            path = _os.path.join(base, _os.path.basename(name))
            if not _os.path.isfile(path):
                return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
            mt = "application/javascript" if path.endswith(".js") else None
            return FileResponse(path, media_type=mt,
                                headers={"Cache-Control": "no-cache"})

        _app.add_api_route("/app/{name}", _app_asset, methods=["GET"])
        def _upload_file(path: str):
            from fastapi.responses import FileResponse, JSONResponse
            import os as _os
            base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                 "static", "uploads")
            full = _os.path.normpath(_os.path.join(base, path))
            if not full.startswith(_os.path.normpath(base)) or not _os.path.isfile(full):
                return JSONResponse({"ok": False}, status_code=404)
            return FileResponse(full, headers={"Cache-Control": "public, max-age=86400"})

        def _root_static(name: str, media: str = None):
            from fastapi.responses import FileResponse, JSONResponse
            import os as _os
            base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "static")
            full = _os.path.join(base, name)
            if not _os.path.isfile(full):
                return JSONResponse({"ok": False}, status_code=404)
            return FileResponse(full, media_type=media,
                                headers={"Cache-Control": "no-cache",
                                         "Service-Worker-Allowed": "/"})

        _app.add_api_route("/sw.js", lambda: _root_static("sw.js", "application/javascript"), methods=["GET"])
        _app.add_api_route("/manifest.webmanifest",
                           lambda: _root_static("app/manifest.webmanifest", "application/manifest+json"),
                           methods=["GET"])
        _app.add_api_route("/uploads/{path:path}", _upload_file, methods=["GET"])
        _app.add_api_route("/app", _app_page, methods=["GET"])
        _app.add_api_route("/ds", _ds_page, methods=["GET"])
        _app.add_api_route("/home", _home_page, methods=["GET"])
        _app.add_api_route("/voice", _voice_page, methods=["GET"])
        _app.add_api_route("/menu", _menu_page, methods=["GET"])
        _app.add_api_route("/piano", _piano_page, methods=["GET"])
        _app.add_api_route("/keys", _keys_page, methods=["GET"])
        _app.add_api_route("/notice", _notice_page, methods=["GET"])
        _app.add_api_route("/ab", _ab_page, methods=["GET"])
        _app.add_api_route("/bg/{name}", _bg_image, methods=["GET"])
        try:
            _app.add_middleware(RootSwitch)
            print("[启动] / → 新界面，旧界面在 /old", flush=True)
        except Exception as _e:
            print(f"[启动] RootSwitch 挂载失败（忽略，仍可用 /app）：{_e}", flush=True)
        try:
            from core import api_json as _api_json
            _api_json.register(_app)
            from core import api_profile as _api_prof
            _api_prof.register(_app)
            from core import api_more as _api_more
            _api_more.register(_app)
            from core import api_story as _api_story
            _api_story.register(_app)
            from core import api_melody as _api_melody
            _api_melody.register(_app)
            print("[接口] JSON API 已挂载", flush=True)
        except Exception as _e:
            print(f"[接口] JSON API 挂载失败：{_e}", flush=True)

        from fastapi import Request as _SceneReq
        from fastapi.responses import JSONResponse as _SceneJSON

        @_app.post("/api/scene/act")
        async def _api_scene_act(request: _SceneReq):
            try:
                data = await request.json()
            except Exception:
                data = {}
            return _SceneJSON(_scene_act(data if isinstance(data, dict) else {}))
    except Exception as _e:
        print(f"[剧情] 播放页路由挂载失败：{_e}", flush=True)
    try:
        _app.add_middleware(IPBlockMiddleware)
    except Exception as _e:
        # 挂不上就放行所有请求，绝不因为拦截功能把站点搞挂
        print(f"[IP拦截] 中间件挂载失败，全部放行：{_e}", flush=True)
    return _app
