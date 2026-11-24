# -*- coding: utf-8 -*-
"""给自写前端用的一套 JSON 接口

不复用 Gradio 的 /gradio_api/call/*，因为那些端点的输出里
gr.State 会被序列化成 null（拿不到 user_id），形状也不好用。

这一套全部返回普通 JSON。
"""
import json
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
            imgs = d.get("images") or []
            last = None
            for out in _A.respond(message, history, user_id, session_id, persona, None,
                                  attachments=imgs):
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

            try:
                from services import chat as _chat_mod
                _recalled = _chat_mod.pop_last_recall(user_id)
            except Exception:
                _recalled = []

            return {
                "ok": True,
                "recalled_ids": _recalled,
                "segs": new_segs,
                "history": chatbot,
                "session_id": session_id,
                "ring": _ring_json(user_id, persona),
            }
        except Exception as e:
            print("[api] 聊天失败：%s" % e, flush=True)
            import traceback; traceback.print_exc()
            return {"ok": False, "error": str(e)}

    # ===== 消息：软删除 / 恢复 / 引用 =====
    @app.post("/api/msg/delete")
    async def _msg_delete(request: Request):
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            mid = d.get("id")
            if not u or not mid:
                return {"ok": False, "error": "参数不对"}
            ok = repo.soft_delete_message(mid, u)
            return {"ok": bool(ok)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/msg/restore")
    async def _msg_restore(request: Request):
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            mid = d.get("id")
            if not u or not mid:
                return {"ok": False, "error": "参数不对"}
            ok = repo.restore_message(mid, u)
            return {"ok": bool(ok)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ===== Web Push =====
    @app.get("/api/push/key")
    def _push_key():
        try:
            from core import push as _push
            return {"ok": True, "key": _push.public_key()}
        except Exception as e:
            return {"ok": False, "key": "", "error": str(e)}

    @app.post("/api/push/subscribe")
    async def _push_sub(request: Request):
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            sub = d.get("sub") or {}
            from core import push as _push
            ok = _push.save_sub(u, sub)
            return {"ok": bool(ok)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/push/test")
    async def _push_test(request: Request):
        """给自己推一条测试（管理员）。"""
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            if not u:
                return {"ok": False, "error": "参数不对"}
            from core import push as _push
            n = _push.send_to_user(u, "陪你", "她：我在。点开看看？", "/app")
            return {"ok": n > 0, "sent": n}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ===== 主动消息偏好 =====
    @app.get("/api/proactive/prefs")
    def _pro_get(u: str = ""):
        try:
            from core import proactive as _pro
            p = _pro.prefs_of(u)
            return {"ok": True, **p, "mode": p.get("mode", "model")}
        except Exception as e:
            return {"ok": False, "error": str(e),
                    "enabled": True, "window": "any", "freq": 1}

    @app.post("/api/proactive/prefs")
    async def _pro_set(request: Request):
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            if not u:
                return {"ok": False, "error": "参数不对"}
            enabled = 1 if d.get("enabled") else 0
            window = (d.get("window") or "any").strip()
            if window not in ("any", "morning", "night"):
                window = "any"
            try:
                freq = int(d.get("freq") or 1)
            except Exception:
                freq = 1
            if freq not in (1, 3, 7):
                freq = 1
            pmode = (d.get("mode") or "model").strip()
            if pmode not in ("model", "rule"):
                pmode = "model"
            conn = repo.get_conn()
            conn.execute(
                "UPDATE users SET proactive_enabled=?, proactive_window=?, proactive_freq=?, "
                "proactive_mode=? WHERE user_id=?", (enabled, window, freq, pmode, u))
            conn.commit()
            conn.close()
            return {"ok": True, "enabled": bool(enabled), "window": window,
                    "freq": freq, "mode": pmode}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/upload")
    async def _upload(request: Request):
        """收一张图：base64 JSON → static/uploads/<uid>/<uuid>.<ext>"""
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            b64 = d.get("data") or ""
            if not u or not b64:
                return {"ok": False, "error": "参数不对"}
            if "," in b64[:80]:
                b64 = b64.split(",", 1)[1]
            import base64 as _b64, uuid as _uuid, os as _os
            raw = _b64.b64decode(b64)
            if len(raw) > 6 * 1024 * 1024:
                return {"ok": False, "error": "图太大了（上限 6 MB）"}
            ext = "jpg"
            if raw[:8] == b"\x89PNG\r\n\x1a\n":
                ext = "png"
            elif raw[:6] in (b"GIF87a", b"GIF89a"):
                ext = "gif"
            elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                ext = "webp"
            base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                                 "static", "uploads", u[:36])
            _os.makedirs(base, exist_ok=True)
            name = "%s.%s" % (_uuid.uuid4().hex, ext)
            with open(_os.path.join(base, name), "wb") as f:
                f.write(raw)
            return {"ok": True, "url": "/uploads/%s/%s" % (u[:36], name)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/msg/recall")
    async def _msg_recall(request: Request):
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            mid = d.get("id")
            by = (d.get("by") or "user").strip()
            if not u or not mid:
                return {"ok": False, "error": "参数不对"}
            from db import repository as _r
            ok = _r.recall_message(mid, u, by)
            # 让她"记住这件事"，但只记事件不记原文
            if ok and by == "user":
                try:
                    _r.upsert_memory(u, (d.get("p") or ""), "moment:他撤回了一句话",
                                     "他说了一句又收回去了，没解释", 3)
                except Exception:
                    pass
            return {"ok": bool(ok)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/msg/deleted")
    def _msg_deleted(u: str = "", limit: int = 50):
        """最近删除的消息，用于找回。"""
        try:
            if not u:
                return {"ok": False, "items": []}
            conn = repo.get_conn()
            conn.row_factory = None
            rows = conn.execute(
                "SELECT id, role, persona, content, deleted_at FROM messages "
                "WHERE user_id=? AND deleted_at IS NOT NULL "
                "ORDER BY deleted_at DESC LIMIT ?",
                (u, limit),
            ).fetchall()
            conn.close()
            items = [{"id": r[0], "role": r[1], "persona": r[2],
                      "content": (r[3] or "")[:200], "deleted_at": r[4]} for r in rows]
            return {"ok": True, "items": items}
        except Exception as e:
            return {"ok": False, "items": [], "error": str(e)}

    @app.post("/api/msg/quote")
    async def _msg_quote(request: Request):
        """给「刚刚发出去那条」打上引用标记。"""
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            p = (d.get("p") or "").strip()
            rid = d.get("reply_to")
            if not u or not rid:
                return {"ok": False, "error": "参数不对"}
            conn = repo.get_conn()
            cur = conn.execute(
                "UPDATE messages SET reply_to=? WHERE id=("
                " SELECT id FROM messages WHERE user_id=? AND persona=? AND role='user'"
                " AND deleted_at IS NULL ORDER BY id DESC LIMIT 1)",
                (rid, u, p),
            )
            conn.commit()
            n = cur.rowcount
            conn.close()
            return {"ok": n > 0}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ===== DeepSeek 应急入口（不是她，是通用助手） =====
    _DS_WHITELIST = {"XIAO2026"}
    _ds_hits = {}

    def _ds_allowed(user_id: str) -> bool:
        """只有管理员 / 白名单能用，防止别人白烧 key。"""
        if not user_id:
            return False
        try:
            conn = repo.get_conn()
            conn.row_factory = None
            row = conn.execute(
                "SELECT username, COALESCE(role,'') FROM users WHERE user_id=?",
                (user_id,),
            ).fetchone()
            conn.close()
            if not row:
                return False
            username, role = row[0] or "", (row[1] or "").lower()
            return role in ("admin", "owner") or username in _DS_WHITELIST
        except Exception:
            return False

    def _ds_rate_ok(user_id: str) -> bool:
        """每人每分钟最多 12 次。"""
        import time as _t
        now = _t.time()
        arr = [x for x in _ds_hits.get(user_id, []) if now - x < 60]
        if len(arr) >= 12:
            _ds_hits[user_id] = arr
            return False
        arr.append(now)
        _ds_hits[user_id] = arr
        return True

    @app.post("/api/ds")
    async def _ds(request: Request):
        try:
            d = await request.json()
            u = (d.get("u") or "").strip()
            msgs = d.get("messages") or []
            if not msgs:
                return {"ok": False, "error": "空消息"}
            if not _ds_allowed(u):
                return {"ok": False, "error": "这个入口只对管理员开放"}
            if not _ds_rate_ok(u):
                return {"ok": False, "error": "太快了，等一分钟"}

            from core import client as _cli
            buf = []
            for delta, _u in _cli.stream_chat(msgs, temperature=0.7, max_tokens=2000):
                if delta:
                    buf.append(delta)
            return {"ok": True, "text": "".join(buf)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ===== DS 网页端：会话 + 流式 =====
    def _ds_ensure():
        from core import ds_chat
        ds_chat.ensure_schema()

    @app.get("/api/ds/convos")
    def _ds_convos(u: str = ""):
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放", "items": []}
        _ds_ensure()
        from core import ds_chat
        return {"ok": True, "items": ds_chat.list_convos(u)}

    @app.post("/api/ds/convo")
    async def _ds_convo_new(request: Request):
        d = await request.json()
        u = (d.get("u") or "").strip()
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放"}
        _ds_ensure()
        from core import ds_chat
        cid = ds_chat.create_convo(u, d.get("title") or "新对话", d.get("model") or "deepseek-chat")
        return {"ok": True, "id": cid}

    @app.post("/api/ds/convo/delete")
    async def _ds_convo_del(request: Request):
        d = await request.json()
        u = (d.get("u") or "").strip()
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放"}
        _ds_ensure()
        from core import ds_chat
        ds_chat.delete_convo(u, d.get("id") or "")
        return {"ok": True}

    @app.post("/api/ds/convo/rename")
    async def _ds_convo_rename(request: Request):
        d = await request.json()
        u = (d.get("u") or "").strip()
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放"}
        _ds_ensure()
        from core import ds_chat
        ds_chat.rename_convo(u, d.get("id") or "", d.get("title") or "新对话")
        return {"ok": True}

    @app.get("/api/ds/msgs")
    def _ds_msgs(u: str = "", id: str = ""):
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放", "items": []}
        _ds_ensure()
        from core import ds_chat
        return {"ok": True, "items": ds_chat.get_msgs(id)}

    @app.post("/api/ds/stream")
    async def _ds_stream(request: Request):
        from fastapi.responses import StreamingResponse
        d = await request.json()
        u = (d.get("u") or "").strip()
        cid = (d.get("id") or "").strip()
        text = (d.get("text") or "").strip()
        model = (d.get("model") or "deepseek-chat").strip()
        thinking = bool(d.get("thinking"))
        system = (d.get("system") or "").strip()

        if not _ds_allowed(u):
            return JSONResponse({"ok": False, "error": "只对管理员开放"}, status_code=403)
        if not _ds_rate_ok(u):
            return JSONResponse({"ok": False, "error": "太快了，等一分钟"}, status_code=429)
        if not text:
            return JSONResponse({"ok": False, "error": "空消息"}, status_code=400)

        _ds_ensure()
        from core import ds_chat, client as _cli
        if not cid:
            cid = ds_chat.create_convo(u, text[:18], model)
        ds_chat.add_msg(cid, "user", text)
        ds_chat.touch_convo(u, cid, model,
                            None if ds_chat.get_msgs(cid)[:-1] else text[:18])

        tier = (d.get("tier") or "mid").strip()
        budget = ds_chat.tier_chars(tier)

        sys_extra = ""
        if d.get("search"):
            try:
                from core import ds_tools as _tools
                hit = _tools.search_block(text[:80])
                if hit:
                    sys_extra = hit
            except Exception as _e:
                print("[DS 搜索] 失败:", _e, flush=True)

        file_block = ""
        try:
            blocks = ds_chat.file_texts(cid)
            if blocks:
                file_block = "\n\n".join("[文件：%s]\n%s" % (n, c) for n, c in blocks)
        except Exception:
            pass

        merged_system = "\n\n".join(x for x in (system, file_block, sys_extra) if x)
        msgs = ds_chat.build_context(cid, merged_system, budget=budget)
        prompt_chars = sum(len(str(m.get("content") or "")) for m in msgs)

        def gen():
            parts = []
            try:
                yield "data: " + json.dumps({"cid": cid}, ensure_ascii=False) + "\n\n"
                extra = {"thinking": {"type": "enabled" if thinking else "disabled"}}
                for delta, _u2 in _cli.stream_chat(
                        msgs, temperature=0.7, max_tokens=8000, model=model,
                        extra_body=extra):
                    if delta:
                        parts.append(delta)
                        yield "data: " + json.dumps({"t": delta}, ensure_ascii=False) + "\n\n"
                full = "".join(parts)
                ds_chat.add_msg(cid, "assistant", full)
                # ===== 计费：按 API 价三倍 =====
                try:
                    from core import ds_tools as _tools
                    pt = _tools.estimate_tokens(str(prompt_chars))
                    ct = _tools.estimate_tokens(full)
                    fee = _tools.cost_yuan(pt, ct)
                    bal = ds_chat.spend(u, fee)
                    yield "data: " + json.dumps({"done": True, "len": len(full),
                                                         "cost": round(fee, 4), "balance": round(bal, 4),
                                                         "tokens": pt + ct}, ensure_ascii=False) + "\n\n"
                except Exception as _e:
                    yield "data: " + json.dumps({"done": True, "len": len(full), "cost": 0,
                                                         "error": str(_e)[:80]}, ensure_ascii=False) + "\n\n"
            except Exception as e:
                yield "data: " + json.dumps({"err": str(e)[:300]}, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.get("/api/ds/balance")
    def _ds_balance(u: str = ""):
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放", "balance": 0}
        _ds_ensure()
        from core import ds_chat, ds_tools
        return {"ok": True, "balance": round(ds_chat.balance_of(u), 4),
                "tiers": [{"key": k, "label": v["label"], "chars": v["chars"]}
                          for k, v in ds_chat.TIERS.items()],
                "markup": ds_tools.MARKUP}

    @app.post("/api/ds/upload")
    async def _ds_upload(request: Request):
        import base64 as _b64
        import os as _os
        import uuid as _uuid
        d = await request.json()
        u = (d.get("u") or "").strip()
        cid = (d.get("id") or "").strip()
        name = (d.get("name") or "file.txt").strip()
        data = d.get("data") or ""
        if not _ds_allowed(u):
            return {"ok": False, "error": "只对管理员开放"}
        _ds_ensure()
        from core import ds_chat, ds_tools
        if not cid:
            cid = ds_chat.create_convo(u, name[:18])
        root = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                             "static", "uploads", "ds")
        _os.makedirs(root, exist_ok=True)
        ext = _os.path.splitext(name)[1][:10] or ".txt"
        path = _os.path.join(root, _uuid.uuid4().hex + ext)
        try:
            raw = _b64.b64decode(data.split(",")[-1])
            with open(path, "wb") as f:
                f.write(raw)
        except Exception as e:
            return {"ok": False, "error": "文件写入失败：%s" % e}
        text = ds_tools.read_file(path)
        if not text:
            return {"ok": False, "error": "这个格式读不出文字（支持 txt/md/py/json/csv/docx/pdf）"}
        fid = ds_chat.add_file(cid, name, text)
        return {"ok": True, "id": cid, "fid": fid, "name": name,
                "chars": len(text), "preview": text[:160]}

    @app.get("/api/ds/fs")
    def _ds_files(u: str = "", id: str = ""):
        if not _ds_allowed(u):
            return {"ok": False, "items": []}
        _ds_ensure()
        from core import ds_chat
        return {"ok": True, "items": ds_chat.list_files(id)}

    @app.get("/api/memories")
    def _memories(u: str = "", p: str = "", limit: int = 200):
        """给星图用：这个人的记忆点。"""
        try:
            if not u:
                return {"ok": False, "items": []}
            items = repo.list_all_memories(u, limit=limit)
            out = []
            for m in items or []:
                out.append({
                    "key": m.get("key") or "",
                    "value": (m.get("value") or "")[:160],
                    "persona": m.get("persona") or "",
                    "priority": m.get("priority") or 1,
                    "ts": str(m.get("updated_at") or ""),
                    "pinned": bool(m.get("pinned")),
                })
            return {"ok": True, "items": out}
        except Exception as e:
            return {"ok": False, "items": [], "error": str(e)}

    @app.get("/api/state")
    def _state(u: str = "", p: str = ""):
        if not u or not p:
            return {"ok": False}
        return {"ok": True, "ring": _ring_json(u, p)}

    # ===== 模式：陪伴 / 恋爱 =====
    @app.get("/api/mode")
    def _get_mode(u: str = "", p: str = ""):
        try:
            from core import mode as mode_mod
            m = mode_mod.get_mode(u, p)
            return {"ok": True, "mode": m}
        except Exception as e:
            return {"ok": False, "mode": "romance", "error": str(e)}

    @app.post("/api/mode")
    async def _set_mode(request: Request):
        try:
            body = await request.json()
            u = (body.get("u") or "").strip()
            pn = (body.get("p") or "").strip()
            m = (body.get("mode") or "").strip().lower()
            if not u or m not in ("companion", "romance"):
                return {"ok": False, "error": "参数不对"}
            from core import mode as mode_mod
            mode_mod.set_mode(u, m, pn)
            # 切换是"关系变更"，写一条里程碑，界面可以据此显示一次对话
            try:
                repo.add_milestone(u, "*", "mode_" + m, "关系改成" + ("陪伴" if m == "companion" else "恋爱"))
            except Exception:
                pass
            return {"ok": True, "mode": mode_mod.get_mode(u, pn)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
