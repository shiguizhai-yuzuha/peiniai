# -*- coding: utf-8 -*-
"""功能主页的接口 —— 个人页 / 记忆 / 换背景 / 记忆模式 / 导出

全部普通 JSON，给自写前端用。
"""
import os

from fastapi import Request
from fastapi.responses import PlainTextResponse

from db import repository as repo
from db.database import get_conn


def _memories(user_id, persona, limit=60):
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT key, value, priority, pinned, updated_at FROM memories "
            "WHERE user_id=? AND persona=? ORDER BY pinned DESC, priority DESC, updated_at DESC "
            "LIMIT ?", (user_id, persona, limit)).fetchall()
        conn.close()
        return [{"key": r["key"], "value": r["value"],
                 "priority": r["priority"], "pinned": bool(r["pinned"]),
                 "at": str(r["updated_at"] or "")[:16]} for r in rows]
    except Exception as e:
        print("[api] 记忆读取失败：%s" % e, flush=True)
        return []


def _memories_all(user_id, limit=999):
    """这个人所有角色的记忆。"""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT persona, key, value FROM memories WHERE user_id=? "
            "ORDER BY persona, priority DESC, updated_at DESC LIMIT ?",
            (user_id, limit)).fetchall()
        conn.close()
        return [{"persona": r["persona"], "key": r["key"], "value": r["value"]}
                for r in rows]
    except Exception:
        return []


def _milestones(user_id, persona):
    try:
        from core import milestones as ms
        if hasattr(ms, "list_for"):
            return ms.list_for(user_id, persona)
        if hasattr(ms, "all_done"):
            return ms.all_done(user_id, persona)
        return []
    except Exception:
        return []


def register(app):

    @app.get("/api/profile")
    def _profile(u: str = "", p: str = ""):
        """个人页要的全部东西，一次拿完。"""
        if not u or not p:
            return {"ok": False, "error": "缺参数"}
        out = {"ok": True, "user_id": u, "persona": p}

        try:
            conn = get_conn()
            row = conn.execute(
                "SELECT nickname, created_at, balance, total_tokens, "
                "memory_mode, reply_style, quiet_start, quiet_end "
                "FROM users WHERE user_id=?", (u,)).fetchone()
            ch = conn.execute(
                "SELECT intimacy, trust, emotion_score, energy, energy_now, "
                "confessed_at, certainty FROM user_characters "
                "WHERE user_id=? AND persona=?", (u, p)).fetchone()
            nmsg = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE user_id=? AND persona=?",
                (u, p)).fetchone()[0]
            nday = conn.execute(
                "SELECT COUNT(DISTINCT DATE(created_at)) FROM messages "
                "WHERE user_id=? AND persona=?", (u, p)).fetchone()[0]
            conn.close()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        out["user"] = {
            "nickname": (row["nickname"] if row else "") or "",
            "created_at": str(row["created_at"] or "")[:10] if row else "",
            "balance": row["balance"] if row else 0,
            "memory_mode": (row["memory_mode"] if row else "") or "mixed",
            "reply_style": (row["reply_style"] if row else "") or "",
        }
        out["char"] = {
            "intimacy": round(float(ch["intimacy"] or 0), 1) if ch else 0,
            "trust": round(float(ch["trust"] or 0), 1) if ch else 0,
            "confessed": bool(ch["confessed_at"]) if ch else False,
            "certainty": round(float(ch["certainty"] or 0), 1) if ch else 0,
        }
        out["stats"] = {"messages": nmsg, "days": nday,
                        "memories": len(_memories(u, p, 999))}
        out["memories"] = _memories(u, p)
        out["milestones"] = _milestones(u, p)
        try:
            from core import scene_runtime
            out["ring"] = scene_runtime.state_of(u, p)
        except Exception:
            out["ring"] = {}
        return out

    @app.get("/api/bglist")
    def _bglist():
        """所有可选的背景图。"""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(base, "static")
        items = []
        try:
            for f in sorted(os.listdir(d)):
                if not f.lower().endswith((".jpg", ".png", ".jpeg", ".webp")):
                    continue
                if f.endswith("_v.jpg") or f.endswith("_v.png"):
                    continue
                if f.startswith("bg_"):
                    items.append({"file": f, "name": f.replace("bg_", "").replace(".jpg", "")})
                    # 文件名 → 角色中文名（config 那张表反过来用）
                    try:
                        from config import CHARACTER_BACKGROUNDS as _CB
                        _rev = {}
                        for _who, _path in (_CB or {}).items():
                            _rev[os.path.basename(str(_path))] = _who
                        for _it in items:
                            _it["label"] = _rev.get(_it["file"], _it["name"])
                    except Exception:
                        for _it in items:
                            _it["label"] = _it["name"]
        except Exception:
            pass
        return {"ok": True, "list": items}

    @app.post("/api/setbg")
    async def _setbg(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        f = (d.get("file") or "").strip()
        if not u or not p:
            return {"ok": False, "error": "缺参数"}
        try:
            if not f:
                repo.delete_user_bg(u, p)
                return {"ok": True, "file": ""}
            path = "static/" + f
            if not os.path.exists(path):
                return {"ok": False, "error": "图片不存在"}
            repo.set_user_bg(u, p, path)
            return {"ok": True, "file": f}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/memory_mode")
    async def _memory_mode(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        mode = (d.get("mode") or "").strip()
        if not u:
            return {"ok": False, "error": "参数不对"}
        try:
            from core import memory_state as _ms
            # 只认两种：纯记忆 / 混合。传 None 表示跟随全局。
            m = mode if mode in ("pure", "mixed") else None
            _ms.set_user_mode(u, m)
            return {"ok": True, "mode": m or "auto"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/pin_memory")
    async def _pin(request: Request):
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        k = (d.get("key") or "").strip()
        pinned = bool(d.get("pinned"))
        if not (u and p and k):
            return {"ok": False, "error": "缺参数"}
        try:
            conn = get_conn()
            conn.execute("UPDATE memories SET pinned=? WHERE user_id=? AND persona=? AND key=?",
                         (1 if pinned else 0, u, p, k))
            conn.commit(); conn.close()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/export")
    def _export(u: str = "", p: str = ""):
        """把她的对话和记忆导出成纯文本。"""
        if not u or not p:
            return PlainTextResponse("缺参数", status_code=400)
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE user_id=? AND persona=? ORDER BY id", (u, p)).fetchall()
            conn.close()
        except Exception as e:
            return PlainTextResponse("读取失败：%s" % e, status_code=500)

        lines = ["# 和 %s 的对话" % p, ""]
        for r in rows:
            who = "我" if r["role"] == "user" else p
            c = (r["content"] or "").replace("<msg>", "\n")
            lines.append("[%s] %s：%s" % (str(r["created_at"] or "")[:16], who, c))
        lines += ["", "# 她记得的事", ""]
        for m in _memories(u, p, 999):
            lines.append("- %s：%s" % (m["key"], m["value"]))

        return PlainTextResponse("\n".join(lines),
                                 headers={"Content-Disposition":
                                          "attachment; filename=chat.txt"})

    @app.get("/api/global")
    def _global(u: str = ""):
        """全局功能页要的东西：不分角色，一次拿全。"""
        if not u:
            return {"ok": False, "error": "缺参数"}

        try:
            conn = get_conn()
            user = conn.execute(
                "SELECT nickname, created_at, balance, memory_mode, reply_style "
                "FROM users WHERE user_id=?", (u,)).fetchone()
            chars = conn.execute(
                "SELECT persona, intimacy, trust, confessed_at FROM user_characters "
                "WHERE user_id=? ORDER BY intimacy DESC", (u,)).fetchall()
            nmsg = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE user_id=?", (u,)).fetchone()[0]
            nday = conn.execute(
                "SELECT COUNT(DISTINCT DATE(created_at)) FROM messages WHERE user_id=?",
                (u,)).fetchone()[0]
            memrows = conn.execute(
                "SELECT persona, key, value, pinned, updated_at FROM memories "
                "WHERE user_id=? ORDER BY persona, pinned DESC, updated_at DESC",
                (u,)).fetchall()
            conn.close()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        # 记忆按角色分组
        groups = {}
        for r in memrows:
            groups.setdefault(r["persona"], []).append({
                "key": r["key"], "value": r["value"],
                "pinned": bool(r["pinned"]),
                "at": str(r["updated_at"] or "")[:10],
            })

        return {
            "ok": True,
            "user": {
                "nickname": (user["nickname"] if user else "") or "",
                "created_at": str(user["created_at"] or "")[:10] if user else "",
                "balance": user["balance"] if user else 0,
                "memory_mode": (user["memory_mode"] if user else "") or "auto",
            },
            "stats": {
                "messages": nmsg, "days": nday,
                "memories": len(memrows), "personas": len(chars),
            },
            "personas": [{
                "persona": c["persona"],
                "intimacy": round(float(c["intimacy"] or 0), 1),
                "trust": round(float(c["trust"] or 0), 1),
                "confessed": bool(c["confessed_at"]),
                "memories": len(groups.get(c["persona"], [])),
            } for c in chars],
            "memories": groups,
        }

    @app.post("/api/setbg_all")
    async def _setbg_all(request: Request):
        """给这个人的所有角色设同一张背景（不分角色）。"""
        try:
            d = await request.json()
        except Exception:
            d = {}
        u = (d.get("user_id") or "").strip()
        f = (d.get("file") or "").strip()
        if not u:
            return {"ok": False, "error": "缺参数"}
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT persona FROM user_characters WHERE user_id=?", (u,)).fetchall()
            conn.close()
            names = [r["persona"] for r in rows]
            for p in names:
                if not f:
                    repo.delete_user_bg(u, p)
                else:
                    repo.set_user_bg(u, p, "static/" + f)
            return {"ok": True, "count": len(names), "file": f}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/export_all")
    def _export_all(u: str = ""):
        """把这个人所有角色的对话和记忆导出。"""
        if not u:
            return PlainTextResponse("缺参数", status_code=400)
        try:
            conn = get_conn()
            rows = conn.execute(
                "SELECT persona, role, content, created_at FROM messages "
                "WHERE user_id=? ORDER BY persona, id", (u,)).fetchall()
            conn.close()
        except Exception as e:
            return PlainTextResponse("读取失败：%s" % e, status_code=500)

        out, cur = ["# 全部对话", ""], None
        for r in rows:
            if r["persona"] != cur:
                cur = r["persona"]
                out += ["", "## " + str(cur), ""]
            who = "我" if r["role"] == "user" else cur
            c = (r["content"] or "").replace("<msg>", "\n")
            out.append("[%s] %s：%s" % (str(r["created_at"] or "")[:16], who, c))
        out += ["", "# 全部记忆", ""]
        for m in _memories_all(u):
            out.append("- [%s] %s：%s" % (m["persona"], m["key"], m["value"]))

        return PlainTextResponse("\n".join(out),
                                 headers={"Content-Disposition":
                                          "attachment; filename=all.txt"})
