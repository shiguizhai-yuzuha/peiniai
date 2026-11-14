# -*- coding: utf-8 -*-
"""剩下的功能搬成 JSON：里程碑 / 我的角色 / 导入 / 剧情 / 纪念册"""
import uuid

from fastapi import Request

from db import repository as repo


def register(app):

    # ---------------- 我的自定义角色 ----------------
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

    # ---------------- 导入聊天记录 ----------------
    @app.post("/api/import")
    async def _import(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        raw = d.get("text") or ""
        my_name = (d.get("my_name") or "").strip()
        if not (u and p and raw):
            return {"ok": False, "error": "缺内容"}

        try:
            from core import chat_import
            prof = chat_import.extract(raw, my_name) or {}
        except Exception as e:
            return {"ok": False, "error": "解析失败：%s" % e}

        # 把提炼出来的东西写进记忆
        saved = 0
        try:
            conn = repo.get_conn()
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
            conn.close()
        except Exception as e:
            return {"ok": False, "error": "写入失败：%s" % e}

        return {"ok": True, "count": saved}

    # ---------------- 里程碑 ----------------
    @app.get("/api/milestones")
    def _milestones(u: str = "", p: str = ""):
        if not u or not p:
            return {"ok": False, "error": "缺参数"}
        try:
            import app as _A
            out = _A.open_milestones(u, p)

            # open_milestones 返回 (gr.update, gr.update, html) —— 只取字符串那段
            html = ""
            if isinstance(out, (list, tuple)):
                for x in out:
                    if isinstance(x, str) and len(x) > len(html):
                        html = x
            elif isinstance(out, str):
                html = out

            if not html.strip():
                return {"ok": False, "error": "没有内容", "html": ""}
            return {"ok": True, "html": html}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 剧情 ----------------
    @app.get("/api/story_list")
    def _story_list(u: str = ""):
        if not u:
            return {"ok": False, "html": ""}
        try:
            import app as _A
            fn = getattr(_A, "_story_list_md", None)
            html = fn(u) if fn else ""
            return {"ok": True, "html": str(html or "")}
        except Exception as e:
            return {"ok": False, "error": str(e), "html": ""}

    @app.post("/api/story_start")
    async def _story_start(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        origin = (d.get("origin") or "").strip()
        if not u or not p or not origin:
            return {"ok": False, "error": "缺参数"}
        try:
            import app as _A
            out = _A.do_story_start(u, origin, p)
            msg = out[0] if isinstance(out, (list, tuple)) else str(out)
            lst = out[1] if isinstance(out, (list, tuple)) and len(out) > 1 else ""
            return {"ok": True, "msg": str(msg), "list": str(lst)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------- 纪念册 / 导出 ----------------
    @app.get("/api/book")
    def _book(u: str = "", p: str = ""):
        if not u or not p:
            return {"ok": False, "error": "缺参数"}
        try:
            import app as _A
            out = _A.do_export_book(u, p)
            msg = out if isinstance(out, str) else (out[0] if out else "")
            return {"ok": True, "msg": str(msg)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
