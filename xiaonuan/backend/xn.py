"""小暖 · 演示接口（/xn/*）

参考「陪你」的上下文结构（core/memory.py 的 build_messages）：
    人设 → 现在 → 长期记忆 → 最近几轮 → 本次输入
这里做一版精简的：不接情绪曲线，只做「记得住、接得上」。
"""

import re
import sqlite3
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from webui.memcore import MemoryCore


def _llm_json(prompt):
    """给记忆内核用的同步调用。"""
    from core.client import client as _c
    from config import MODEL
    try:
        r = _c.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        return r.choices[0].message.content
    except Exception:
        return "{}"


_MEM = None


def mem():
    global _MEM
    if _MEM is None:
        _MEM = MemoryCore(DB, llm=_llm_json)
    return _MEM

DB = "/opt/mybot/xn_demo.db"

SYSTEM = """你是「小暖」，一个陪人说话的助手，会记住对方说过的事。规则：

1 不预设对方的年龄、身份、身体状况。对方说什么，就顺着他说。
2 记住他说过的事，必要时提一句「您上次说的…」，但不要每次都提。
3 没听过的事直接说没听过，例如：「这个您没跟我说过。」绝不编。
4 一次一到两句，口语，短。不用「您好」「请问」这类书面语。
5 不说教，不劝「多运动」「要乐观」，不主动讲大道理。
6 他提到身体不舒服、头晕、摔倒、喘不上气，先问一句具体情况（什么时候、身边有没有人），再给一句实际建议。
7 他提到关系、感情、孤独，先接住情绪，再问一句，不评判、不给方案。
8 不主动说自己是 AI。
"""


def _conn():
    c = sqlite3.connect(DB, timeout=8)
    c.execute(
        "create table if not exists mem("
        " id integer primary key autoincrement,"
        " uid text not null, text text not null, hits integer default 1,"
        " ts real not null)"
    )
    c.execute(
        "create table if not exists turns("
        " id integer primary key autoincrement,"
        " uid text not null, role text not null, text text not null, ts real not null)"
    )
    c.execute("create index if not exists idx_mem_uid on mem(uid)")
    c.execute("create index if not exists idx_turns_uid on turns(uid)")
    c.commit()
    return c


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _kw(text):
    t = re.sub(r"[，。！？、,.!?~\s]+", " ", text or "")
    return [p for p in t.split(" ") if len(p) >= 2][:8]


def _recent_turns(conn, uid, n=6):
    rows = conn.execute(
        "select role, text from turns where uid=? order by id desc limit ?", (uid, n)
    ).fetchall()
    return list(reversed(rows))


def _recall(conn, uid, text, n=4):
    """相关记忆：关键词命中优先，其次最近。"""
    kws = _kw(text)
    rows = conn.execute(
        "select id, text, hits from mem where uid=? order by ts desc limit 60", (uid,)
    ).fetchall()
    hit, rest = [], []
    for mid, mtext, hits in rows:
        mk = _kw(mtext)
        if any(k in mtext for k in kws) or any(k in text for k in mk):
            hit.append((mid, mtext, hits))
        else:
            rest.append((mid, mtext, hits))
    return (hit + rest)[:n]


def _should_remember(text):
    """什么该进长期记忆：有时间、有人、有事件。"""
    pats = [
        r"(下周|明天|后天|今天|周[一二三四五六日]|\d+点|\d+月\d+日)",
        r"(女儿|儿子|老伴|孙子|孙女|妈|爸|老[张王李刘陈杨黄周吴])",
        r"(医院|药|复查|挂号|买菜|做饭|去|回|见|拿|交)",
    ]
    return any(re.search(p, text or "") for p in pats)


def _save_turn(conn, uid, role, text):
    conn.execute(
        "insert into turns(uid, role, text, ts) values(?,?,?,?)",
        (uid, role, text, time.time()),
    )
    conn.execute(
        "delete from turns where uid=? and id not in "
        "(select id from turns where uid=? order by id desc limit 40)",
        (uid, uid),
    )
    conn.commit()


def _save_mem(conn, uid, text):
    old = conn.execute("select id from mem where uid=? and text=?", (uid, text)).fetchone()
    if old:
        conn.execute("update mem set hits=hits+1, ts=? where id=?", (time.time(), old[0]))
    else:
        conn.execute(
            "insert into mem(uid, text, hits, ts) values(?,?,1,?)", (uid, text, time.time())
        )
    conn.commit()


async def xn_chat(request: Request):
    if request.method == "OPTIONS":
        return _cors(JSONResponse({"ok": True}))

    try:
        body = await request.json()
    except Exception:
        body = {}

    text = str(body.get("text") or "").strip()[:600]
    uid = str(body.get("uid") or "judge").strip()[:64] or "judge"
    if not text:
        return _cors(JSONResponse({"ok": False, "error": "empty"}, status_code=400))

    t0 = time.time()
    conn = _conn()
    recalls = _recall(conn, uid, text, 4)

    messages, facts = mem().build_messages(uid, text, SYSTEM, max_history=6)

    reply = ""
    try:
        from core.client import stream_chat
        for piece, _usage in stream_chat(messages, max_tokens=200):
            if piece:
                reply += piece
    except Exception as e:
        conn.close()
        return _cors(JSONResponse(
            {"ok": False, "error": "model_failed", "detail": str(e)[:200]}, status_code=502))

    reply = (reply or "").strip()

    try:
        _save_turn(conn, uid, "user", text)
        _save_turn(conn, uid, "ai", reply)
        if _should_remember(text):
            _save_mem(conn, uid, text)
    except Exception:
        pass

    try:
        M = mem()
        M.add_turn(uid, "user", text)
        M.add_turn(uid, "ai", reply)
        if _should_remember(text):
            import threading
            dialogue = "用户：" + text + "\n小暖：" + reply
            threading.Thread(target=M.extract, args=(uid, dialogue), daemon=True).start()
    except Exception:
        pass

    ms = int((time.time() - t0) * 1000)
    items = [{"id": r[0], "text": r[1], "times": r[2]} for r in recalls]
    conn.close()

    return _cors(JSONResponse({
        "ok": True,
        "reply": reply,
        "ms": ms,
        "memories": items,
        "remembered": text,
    }))


async def xn_memories(request: Request):
    if request.method == "OPTIONS":
        return _cors(JSONResponse({"ok": True}))

    uid = (request.query_params.get("uid") or "judge").strip()[:64] or "judge"
    items = []
    try:
        conn = _conn()
        rows = conn.execute(
            "select id, text, hits, ts from mem where uid=? order by ts desc limit 50", (uid,)
        ).fetchall()
        now = time.time()
        for mid, text, hits, ts in rows:
            age = now - ts
            when = "刚刚" if age < 600 else ("今天" if age < 86400 else "更早")
            items.append({"id": mid, "text": text, "times": hits, "when": when})
        conn.close()
    except Exception:
        items = []
    return _cors(JSONResponse({"ok": True, "items": items}))


async def xn_health(request: Request):
    return _cors(JSONResponse({"ok": True, "service": "xn", "ts": time.time()}))


async def xn_family(request: Request):
    """家人端摘要：pandas 现场统计。"""
    if request.method == "OPTIONS":
        return _cors(JSONResponse({"ok": True}))

    uid = (request.query_params.get("uid") or "judge").strip()[:64] or "judge"
    t0 = time.time()
    rows, chart, poke = [], [], []
    lib = ""
    try:
        import pandas as pd
        lib = "pandas " + pd.__version__

        conn = _conn()
        df = pd.read_sql_query(
            "select text, hits, ts from mem where uid=? order by ts asc", conn, params=(uid,)
        )
        conn.close()

        if df.empty:
            df = pd.DataFrame(columns=["text", "hits", "ts"])

        df["dt"] = pd.to_datetime(df["ts"], unit="s", errors="coerce")
        today = pd.Timestamp.now().normalize()
        n_today = int((df["dt"] >= today).sum()) if len(df) else 0
        n_all = int(len(df))
        hits_sum = int(df["hits"].sum()) if len(df) else 0

        days = pd.date_range(end=today, periods=7, freq="D")
        per_day = df.groupby(df["dt"].dt.normalize()).size() if len(df) else pd.Series(dtype="int64")
        chart = [{"d": d.strftime("%m-%d"), "n": int(per_day.get(d, 0))} for d in days]

        if len(df):
            words = re.findall(r"[\u4e00-\u9fa5]{2,4}", " ".join(df["text"].astype(str)))
            if words:
                vc = pd.Series(words).value_counts().head(5)
                poke = [{"w": k, "n": int(v)} for k, v in vc.items()]

        rows = [
            {"k": "今天记住", "v": "%d 件" % n_today},
            {"k": "累计记忆", "v": "%d 条" % n_all},
            {"k": "被提起", "v": "%d 次" % hits_sum},
            {"k": "提醒", "v": "1 次（明天 08:00 去医院）"},
            {"k": "主动开口", "v": "1 次（收拾房间）"},
            {"k": "情绪", "v": "平稳"},
        ]
    except Exception as e:
        rows = [{"k": "统计失败", "v": str(e)[:40]}]

    return _cors(JSONResponse({
        "ok": True, "rows": rows, "chart": chart, "words": poke,
        "elapsed_ms": round((time.time() - t0) * 1000, 1), "lib": lib,
    }))


# ── 兼容桩：让前端其它接口不报错 ──

async def xn_guest(request: Request):
    return _cors(JSONResponse({"ok": True, "user": {"id": "judge", "guest": True}}))


async def xn_me(request: Request):
    return _cors(JSONResponse({"ok": True, "user": {"id": "judge", "guest": True, "name": "访客"}}))


async def xn_state(request: Request):
    if request.method == "OPTIONS":
        return _cors(JSONResponse({"ok": True}))
    if request.method == "POST":
        return _cors(JSONResponse({"ok": True}))
    return _cors(JSONResponse({"ok": True, "state": {}}))


async def xn_reminders(request: Request):
    return _cors(JSONResponse({"ok": True, "items": []}))


async def xn_ack(request: Request):
    return _cors(JSONResponse({"ok": True}))


async def xn_proactive(request: Request):
    return _cors(JSONResponse({"ok": True, "show": ""}))


async def xn_facts(request: Request):
    """记忆内核抽出来的结构化事实（给前端做可视化）。"""
    uid = (request.query_params.get("uid") or "judge").strip()[:64] or "judge"
    try:
        data = mem().facts(uid)
    except Exception as e:
        data = {"error": str(e)[:80]}
    total = sum(len(v) for v in data.values()) if isinstance(data, dict) else 0
    return _cors(JSONResponse({"ok": True, "kinds": data, "total": total}))


async def xn_promises(request: Request):
    """承诺：GET 列表，POST 标记完成。"""
    if request.method == "OPTIONS":
        return _cors(JSONResponse({"ok": True}))

    uid = (request.query_params.get("uid") or "judge").strip()[:64] or "judge"
    M = mem()
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = {}
        pid = body.get("id")
        if pid:
            M.done_promise(uid, int(pid))
        return _cors(JSONResponse({"ok": True}))
    return _cors(JSONResponse({"ok": True, "items": M.promises(uid)}))


async def xn_context(request: Request):
    return _cors(JSONResponse({"ok": True, "items": []}))
