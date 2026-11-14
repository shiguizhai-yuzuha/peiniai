# -*- coding: utf-8 -*-
"""给自写前端用的一套 JSON 接口

不复用 Gradio 的 /gradio_api/call/*，因为那些端点的输出里
gr.State 会被序列化成 null（拿不到 user_id），形状也不好用。

这一套全部返回普通 JSON。
"""
import os
import uuid
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse

from db import repository as repo
from core import personas as personas_mod


def _ring_json(user_id, persona):
    """环的四个数字 + 标签。失败不抛。"""
    try:
        from core import ring, scene_runtime
        st = ring.build(user_id, persona)
        rl = scene_runtime.state_of(user_id, persona)
        return {
            "love":   round(float(st["love"]["frac"]) * 100, 1),
            "trust":  round(float(st["confidence"]["frac"]) * 100, 1)
                       if False else round(float(st["trust"]["frac"]) * 100, 1),
            "mood":   rl["mood"],
            "energy": rl["energy"],
            "love_label":  st["love"]["label"],
            "trust_label": st["trust"]["label"],
            "mood_label":  rl["mood_label"],
            "energy_label": rl["energy_label"],
            "state": st["_center"]["state"],
            "stage": st["_center"]["stage"],
            "mem":   st["_mem"],
        }
    except Exception as e:
        print("[api] 环失败：%s" % e, flush=True)
        return {}


def _history_json(user_id, persona):
    try:
        import app as _A
        return _A.load_history(user_id, persona)
    except Exception:
        return []


def register(app):
    """把接口挂到 FastAPI 实例上。"""

    @app.get("/api/personas")
    def _personas():
        try:
            names = list(personas_mod.PERSONAS.keys())
            default = getattr(personas_mod, "DEFAULT_PERSONA", names[0] if names else "")
            return {"ok": True, "personas": names, "default": default}
        except Exception as e:
            return {"ok": False, "error": str(e), "personas": []}

    @app.post("/api/login")
    async def _login(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("username") or "").strip()
        p = d.get("password") or ""
        if not u or not p:
            return {"ok": False, "error": "用户名和密码都要填"}
        try:
            user_id, err = repo.login_user(u, p)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if err:
            return {"ok": False, "error": err}

        import app as _A
        persona = _A.DEFAULT_PERSONA
        hist = _history_json(user_id, persona)
        if not hist:
            try:
                hist = _A.opening_history(persona)
            except Exception:
                hist = []
        return {
            "ok": True, "user_id": user_id, "username": u,
            "persona": persona, "session_id": str(uuid.uuid4()),
            "history": hist, "ring": _ring_json(user_id, persona),
        }

    @app.post("/api/persona")
    async def _persona(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        user_id = (d.get("user_id") or "").strip()
        persona = (d.get("persona") or "").strip()
        if not user_id or not persona:
            return {"ok": False, "error": "缺参数"}
        hist = _history_json(user_id, persona)
        if not hist:
            try:
                import app as _A
                hist = _A.opening_history(persona)
            except Exception:
                hist = []
        return {
            "ok": True, "persona": persona, "history": hist,
            "session_id": str(uuid.uuid4()),
            "ring": _ring_json(user_id, persona),
        }

    @app.post("/api/chat")
    async def _chat(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        user_id = (d.get("user_id") or "").strip()
        persona = (d.get("persona") or "").strip()
        session_id = (d.get("session_id") or "").strip() or str(uuid.uuid4())
        message = (d.get("message") or "").strip()
        history = d.get("history") or []

        if not user_id:
            return {"ok": False, "error": "没登录"}
        if not message:
            return {"ok": False, "error": "空消息"}

        try:
            import app as _A
            last = None
            for out in _A.respond(message, history, user_id, session_id, persona, None):
                last = out
            if last is None:
                return {"ok": False, "error": "没有回复"}

            # respond 吐 6 个：msg / chatbot / relationship_html / typing /
            #                     guest_save_group / guest_end_md
            chatbot = last[1] if len(last) > 1 else []

            # 取出这一轮新加的 assistant 段
            segs = []
            for item in reversed(chatbot):
                if item.get("role") != "assistant":
                    break
                c = item.get("content")
                if isinstance(c, list):
                    c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                segs.append(c or "")
            segs.reverse()
            # 去掉上一轮就已经在 history 里的那几条
            prev = len(history or [])
            new_segs = segs[-max(1, len(segs)):] if prev == 0 else segs[-3:]
            if len(new_segs) > 4:
                new_segs = new_segs[-4:]

            return {
                "ok": True,
                "segs": new_segs,
                "history": chatbot,
                "session_id": session_id,
                "ring": _ring_json(user_id, persona),
            }
        except Exception as e:
            print("[api] 聊天失败：%s" % e, flush=True)
            import traceback; traceback.print_exc()
            return {"ok": False, "error": str(e)}

    @app.get("/api/state")
    def _state(u: str = "", p: str = ""):
        if not u or not p:
            return {"ok": False}
        return {"ok": True, "ring": _ring_json(u, p)}

    @app.get("/api/notice")
    def _notice():
        """启动警告：要不要显示 + 内容。"""
        try:
            import app as _A
            show = bool(getattr(_A, "SHOW_STARTUP_NOTICE", True))
            html = ""
            if show:
                p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "templates", "notice.html")
                with open(p, encoding="utf-8") as f:
                    html = f.read()
            return {"ok": True, "show": show, "html": html}
        except Exception as e:
            return {"ok": False, "show": False, "html": "", "error": str(e)}

    @app.get("/api/bg")
    def _bg(p: str = "", u: str = "", login: int = 0):
        """某个角色的背景图 URL（横版 + 竖版）。"""
        try:
            import app as _A
            import os as _os
            from core import personas as _ps

            img = None
            if login:
                lb = getattr(_A, "LOGIN_BACKGROUND", "")
                if lb and _os.path.exists(lb):
                    img = lb

            if not img and u and p:
                try:
                    ub = repo.get_user_bg(u, p)
                    if ub and ub.get("file") and _os.path.exists(ub["file"]):
                        img = ub["file"]
                except Exception:
                    pass

            if not img and p:
                try:
                    c = _ps.get_background(p)
                    if c and _os.path.exists(c):
                        img = c
                except Exception:
                    pass

            if not img and _os.path.exists("static/bg.jpg"):
                img = "static/bg.jpg"

            if not img:
                return {"ok": True, "url": "", "url_v": ""}

            root, ext = _os.path.splitext(img)
            vp = root + "_v" + ext
            if not _os.path.exists(vp):
                vp = img

            return {"ok": True,
                    "url": _A._bg_url(img),
                    "url_v": _A._bg_url(vp)}
        except Exception as e:
            return {"ok": False, "url": "", "url_v": "", "error": str(e)}

    @app.get("/api/me")
    def _me():
        return {"ok": True, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
