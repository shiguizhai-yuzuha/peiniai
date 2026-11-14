# -*- coding: utf-8 -*-
"""钢琴 · 记忆接口：把她/你弹的存进记忆"""
from fastapi import Request

from db.database import get_conn

# MIDI → 音名，方便写进提示词
_NAME = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def _name(midi):
    try:
        m = int(midi)
    except Exception:
        return "?"
    return "%s%d" % (_NAME[m % 12], m // 12 - 1)


def register(app):

    @app.post("/api/melody")
    async def _melody(request: Request):
        """存一段旋律。

        只存“能被说出来的部分”：几个音、多长、谁弹的。
        不存音频——体积为零，而且她能真的再弹出来。
        """
        try:
            d = await request.json()
        except Exception:
            d = {}

        u = (d.get("user_id") or "").strip()
        p = (d.get("persona") or "").strip()
        notes = d.get("notes") or []
        who = (d.get("who") or "me").strip()      # me = 用户弹的 / her = 她弹的

        if not (u and p) or not isinstance(notes, list) or not notes:
            return {"ok": False, "error": "缺内容"}

        # 只留前 12 个音，写成 "C4 D4 E4 ..."
        head = []
        for n in notes[:12]:
            if isinstance(n, dict):
                head.append(_name(n.get("midi")))
            else:
                head.append(_name(n))
        seq = " ".join(head)
        n_all = len(notes)

        if who == "her":
            value = "她弹了一段琴：%s（共 %d 个音）" % (seq, n_all)
        else:
            value = "你弹给她一段：%s（共 %d 个音）" % (seq, n_all)

        key = ("melody_%s_%s" % (who, str(int(__import__("time").time()))))
        try:
            conn = get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO memories(user_id, persona, key, value, priority) "
                    "VALUES(?,?,?,?,?)", (u, p, key[:40], value[:200], 5))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        return {"ok": True, "seq": seq, "count": n_all}

    @app.get("/api/melodies")
    def _melodies(u: str = "", p: str = ""):
        if not (u and p):
            return {"ok": False, "list": []}
        try:
            conn = get_conn()
            try:
                rows = conn.execute(
                    "SELECT key, value FROM memories "
                    "WHERE user_id=? AND persona=? AND key LIKE 'melody%' "
                    "ORDER BY rowid DESC LIMIT 20", (u, p)).fetchall()
            finally:
                conn.close()
            return {"ok": True, "list": [{"k": r["key"], "v": r["value"]} for r in rows]}
        except Exception as e:
            return {"ok": False, "error": str(e), "list": []}
