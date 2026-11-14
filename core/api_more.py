# -*- coding: utf-8 -*-
"""把旧界面剩下的功能搬成 JSON 接口

注册 / 免登录试聊 / 转正 / 清空 / 改密码 / 偏好 / 里程碑 / 导入 / 自定义角色
全部返回普通 JSON，给自写前端用。
"""
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from db import repository as repo


def _ring(u, p):
    try:
        from core import ring
        st = ring.build(u, p)
        return {
            "love": round(st["love"]["frac"] * 100, 1),
            "trust": round(st["trust"]["frac"] * 100, 1),
            "love_label": st["love"]["label"],
            "trust_label": st["trust"]["label"],
            "state": st["_center"]["state"],
            "stage": st["_center"]["stage"],
            "mem": st["_mem"],
        }
    except Exception:
        return {}


def _ip(request):
    try:
        xff = request.headers.get("x-forwarded-for") or ""
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else ""
    except Exception:
        return ""


def register(app):

    # ---------- 她说话的样子 ----------
    @app.get("/api/voice/get")
    def _voice_get(uid: str = ""):
        from core import voice_cfg
        return {"ok": True, "cfg": voice_cfg.load(uid or None)}

    @app.post("/api/voice/save")
    async def _voice_save(request: Request):
        from core import voice_cfg
        _err = ""
        try:
            data = await request.json()
        except Exception as _e:
            data = {}
            _err = repr(_e)[:120]
        cfg = voice_cfg.normalize(data or {})
        # 没登录（页面没带 uid）就只回显，不落库
        uid = (data or {}).get("uid") or ""
        saved = voice_cfg.save(uid, cfg) if uid else False
        return {"ok": True, "cfg": cfg, "saved": saved, "err": _err}


    # ---------------- 注册 ----------------
    @app.post("/api/register")
    async def _register(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("username") or "").strip()
        p = d.get("password") or ""
        p2 = d.get("password2") or p
        code = (d.get("invite_code") or "").strip()

        if not u or not p:
            return {"ok": False, "error": "用户名和密码都要填"}
        if p != p2:
            return {"ok": False, "error": "两次密码不一致"}

        try:
            import app as _A
            # do_register 返回 5 个：(user_id, msg, update, update, history)
            out = _A.do_register(u, p, p2, code or "GUEST")
            user_id = out[0] if out else None
            msg = out[1] if len(out) > 1 else ""
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not user_id:
            return {"ok": False, "error": (msg or "注册失败").lstrip("❌ ").strip()}

        try:
            import app as _A
            persona = _A.DEFAULT_PERSONA
            hist = _A.load_history(user_id, persona) or []
            if not hist:
                hist = _A.opening_history(persona)
        except Exception:
            persona, hist = "", []

        return {
            "ok": True, "user_id": user_id, "username": u, "persona": persona,
            "session_id": str(uuid.uuid4()), "history": hist,
            "ring": _ring(user_id, persona) if persona else {},
        }

    # ---------------- 免登录试聊 ----------------
    @app.post("/api/guest")
    async def _guest(request: Request):
        ip = _ip(request)
        try:
            from services import guest as G
            tok, err = G.open_session(ip)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not tok:
            return {"ok": False, "error": err or "现在开不了"}

        try:
            persona = G.GUEST_PERSONA
            turns = int(G.turns_left(tok))
            segs = G.to_dict(tok).get("history") or []
        except Exception:
            persona, turns, segs = "大肥鱼", 10, []

        lines = []
        for h in segs:
            if h.get("role") == "assistant":
                lines.append(h.get("content") or "")

        return {
            "ok": True, "token": tok, "persona": persona,
            "turns_left": turns, "opening": lines,
        }

    # ---------------- 游客聊天 ----------------
    @app.post("/api/guest_chat")
    async def _guest_chat(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        tok = (d.get("token") or "").strip()
        msg = (d.get("message") or "").strip()
        if not tok or not msg:
            return {"ok": False, "error": "缺参数"}
        try:
            from services import guest as G, guest_chat as GC
            if G.is_over(tok):
                return {"ok": True, "over": True, "segs": [G.ending_line()]}
            G.append(tok, "user", msg)
            text, segs = GC.ask(tok, G.GUEST_PERSONA, msg)
            G.append(tok, "assistant", text)
            turn = G.bump_turn(tok)
            return {"ok": True, "segs": segs, "turn": turn,
                    "over": G.is_over(tok),
                    "turns_left": int(G.turns_left(tok)),
                    "ending": G.ending_line() if G.is_over(tok) else ""}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 游客转正 ----------------
    @app.post("/api/keep")
    async def _keep(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("username") or "").strip()
        p = d.get("password") or ""
        tok = (d.get("token") or "").strip()
        if not (u and p and tok):
            return {"ok": False, "error": "缺参数"}
        try:
            import app as _A
            out = _A.do_keep(u, p, tok)
            uid = out[0] if out else None
            if not uid:
                return {"ok": False, "error": (out[-1] if out else "失败")}
            hist = out[3] if len(out) > 3 else []
            persona = getattr(_A, "GUEST_PERSONA", "大肥鱼") if False else "大肥鱼"
            return {"ok": True, "user_id": uid, "username": u, "persona": persona,
                    "session_id": str(uuid.uuid4()), "history": hist,
                    "ring": _ring(uid, persona)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 清空对话（真清） ----------------
    @app.post("/api/clear")
    async def _clear(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        if not u or not p:
            return {"ok": False, "error": "缺参数"}
        try:
            import app as _A
            hist, sid = _A.clear_chat()
            hist2 = _A.opening_history(p) or []
            return {"ok": True, "session_id": sid, "history": hist2}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 改密码 ----------------
    @app.post("/api/password")
    async def _password(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        if not u:
            return {"ok": False, "error": "先登录"}
        try:
            import app as _A
            msg = _A.do_change_password(u, d.get("old") or "",
                                        d.get("new") or "", d.get("new2") or d.get("new") or "")
            ok = str(msg).startswith("✅")
            return {"ok": ok, "msg": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 偏好 ----------------
    @app.post("/api/prefs")
    async def _prefs(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        if not u:
            return {"ok": False, "error": "先登录"}
        try:
            import app as _A
            msg = _A.do_save_prefs(
                u, d.get("style") or "normal",
                bool(d.get("quiet_on")),
                d.get("start") or "", d.get("end") or "")
            ok = str(msg).startswith("✅")
            return {"ok": ok, "msg": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 昵称 ----------------
    @app.post("/api/nickname")
    async def _nickname(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        n = (d.get("nickname") or "").strip()[:20]
        if not u:
            return {"ok": False, "error": "先登录"}
        try:
            repo.set_user_pref(u, "nickname", n)
            return {"ok": True, "nickname": n}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 自定义角色 ----------------
    @app.get("/api/my_personas")
    def _my_personas(u: str = ""):
        if not u:
            return {"ok": False, "list": []}
        try:
            from services import keepsake as gkeep
            items = gkeep.list_personas(u) or []
            out = []
            for x in items:
                out.append({"persona": x.get("persona") if isinstance(x, dict) else str(x)})
            return {"ok": True, "list": out}
        except Exception as e:
            return {"ok": False, "error": str(e), "list": []}

    @app.post("/api/delete_persona")
    async def _del_persona(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        if not u:
            return {"ok": False, "error": "先登录"}
        try:
            import app as _A
            out = _A.do_delete_persona(u)
            msg = out[0] if isinstance(out, (list, tuple)) else str(out)
            return {"ok": str(msg).startswith("✅"), "msg": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 导入聊天 ----------------
    @app.post("/api/import")
    async def _import(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        text = d.get("text") or ""
        if not (u and p and text):
            return {"ok": False, "error": "缺内容"}
        try:
            from core import chat_import
            from db.database import get_conn as _gc

            prof = chat_import.extract(text, d.get("my_name") or "") or {}
            saved = 0
            conn = _gc()
            try:
                for k, v in list(prof.items())[:40]:
                    if not v:
                        continue
                    if isinstance(v, (list, tuple)):
                        v = "；".join(str(x) for x in v[:6])
                    v = str(v)[:200]
                    key = ("import_" + str(k))[:40]
                    conn.execute(
                        "INSERT OR REPLACE INTO memories(user_id, persona, key, value, priority) "
                        "VALUES(?,?,?,?,?)", (u, p, key, v, 6))
                    saved += 1
                conn.commit()
            finally:
                conn.close()
            return {"ok": True, "count": saved}
        except Exception as e:
            return {"ok": False, "error": str(e)}
