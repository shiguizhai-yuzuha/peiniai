"""主动消息（独立模块）。

她先开口。这是最容易变成骚扰的功能，所以规则写死在这里：

    一天最多 1 条
    23:30–07:00 不发
    连续 2 天没回 → 3 天 1 条
    连续 5 天没回 → 停 7 天
    用户关了就不发

用法：
    python -m core.proactive --dry-run      # 只看会发什么，不写库
    python -m core.proactive --limit 5      # 真发（最多 5 条）
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "love_bot.db")

# ---- 规则 ----
QUIET_START = 23 * 60 + 30      # 23:30
QUIET_END = 7 * 60              # 07:00
MAX_PER_DAY = 1

SILENCE_HOURS = {               # 沉默多久算"久"
    "A": 24, "B": 18, "C": 12, "D": 8, "lover": 8,
}
COOLDOWN_DAYS = {2: 3, 3: 3, 4: 3, 5: 7}   # 连续没回 N 天 → 冷却几天


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema():
    conn = _conn()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    if "source" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN source TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS proactive_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        persona TEXT NOT NULL,
        trigger TEXT,
        content TEXT,
        sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
        opened_at TEXT
    )""")
    conn.commit()
    conn.close()


# ---------- 判断 ----------

def _minutes_now() -> int:
    n = datetime.now()
    return n.hour * 60 + n.minute


def in_quiet_hours() -> bool:
    m = _minutes_now()
    if QUIET_START <= QUIET_END:
        return QUIET_START <= m < QUIET_END
    return m >= QUIET_START or m < QUIET_END


def last_talk(user_id: str, persona: str):
    conn = _conn()
    row = conn.execute(
        "SELECT created_at FROM messages WHERE user_id=? AND persona=? ORDER BY id DESC LIMIT 1",
        (user_id, persona),
    ).fetchone()
    conn.close()
    if not row or not row["created_at"]:
        return None
    try:
        return datetime.strptime(row["created_at"][:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def last_user_talk(user_id: str, persona: str):
    conn = _conn()
    row = conn.execute(
        "SELECT created_at FROM messages WHERE user_id=? AND persona=? AND role='user' "
        "ORDER BY id DESC LIMIT 1",
        (user_id, persona),
    ).fetchone()
    conn.close()
    if not row or not row["created_at"]:
        return None
    try:
        return datetime.strptime(row["created_at"][:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def sent_today(user_id: str) -> bool:
    conn = _conn()
    row = conn.execute(
        "SELECT count(*) n FROM proactive_log WHERE user_id=? AND date(sent_at)=date('now')",
        (user_id,),
    ).fetchone()
    conn.close()
    return (row["n"] or 0) >= MAX_PER_DAY


def consecutive_silent_days(user_id: str, persona: str) -> int:
    """他连续几天没开口（按最后一条 user 消息算）。"""
    t = last_user_talk(user_id, persona)
    if not t:
        return 99
    return max(0, (datetime.now() - t).days)


def cooling(user_id: str) -> bool:
    conn = _conn()
    row = conn.execute(
        "SELECT sent_at FROM proactive_log WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    if not row or not row["sent_at"]:
        return False
    try:
        t = datetime.strptime(row["sent_at"][:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False
    days_since = (datetime.now() - t).days
    # 上一条之后他回过话吗
    conn = _conn()
    replied = conn.execute(
        "SELECT count(*) n FROM messages WHERE user_id=? AND role='user' AND created_at > ?",
        (user_id, row["sent_at"]),
    ).fetchone()
    conn.close()
    if (replied["n"] or 0) > 0:
        return False
    return days_since < 7


def pick_trigger(user_id: str, persona: str, stage: str):
    """返回 (trigger, 说明) 或 None。"""
    p = prefs_of(user_id)
    if not p["enabled"]:
        return None
    if not _window_ok(p["window"]):
        return None
    if not _freq_ok(user_id, p["freq"]):
        return None
    if in_quiet_hours():
        return None
    if sent_today(user_id):
        return None
    if cooling(user_id):
        return None

    silent_days = consecutive_silent_days(user_id, persona)
    last = last_talk(user_id, persona)
    if not last:
        return None
    hours = (datetime.now() - last).total_seconds() / 3600
    need = SILENCE_HOURS.get(stage or "A", 24)

    # ① 沉默触发
    if hours >= need:
        return ("silence", "沉默了 %.0f 小时" % hours)

    # ② 时间锚点（早上/夜里），只在已经聊过、但不是刚聊完时
    m = _minutes_now()
    if 7 * 60 <= m <= 9 * 60 and hours >= 6:
        return ("morning", "早安档")
    if 21 * 60 <= m <= 23 * 60 and hours >= 3:
        return ("night", "夜里档")

    return None


# ---------- 生成 ----------

def build_message(user_id: str, persona: str, trigger: str) -> str:
    """调模型生成一句她会主动说的话。失败返回空。"""
    from core import client, memory

    conn = _conn()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE user_id=? AND persona=? "
        "ORDER BY id DESC LIMIT 6",
        (user_id, persona),
    ).fetchall()
    conn.close()
    recent = "\n".join(
        ("他：" if r["role"] == "user" else "你：") + (r["content"] or "")[:80]
        for r in reversed(rows)
    )

    try:
        mems = memory.recall(user_id, persona, "", limit=3) if hasattr(memory, "recall") else []
    except Exception:
        mems = []
    mem_txt = "\n".join(str(m)[:60] for m in (mems or [])[:3])

    kind = {"silence": "他有一阵没说话了", "morning": "现在是早上",
            "night": "现在是夜里"}.get(trigger, "你想说点什么")

    sys_prompt = (
        "你在扮演一个陪着他的女孩。现在轮到你主动开口——他还没说话，是你要先说。\n"
        "规则：\n"
        "1. 只说 1 到 2 句，不超过 40 字\n"
        "2. 想提具体的事，只能用【下面的对话或记忆里真的出现过】的内容；"
        "一样都没有，就说得笼统一点，不要造\n"
        "3. 严禁编造：不许出现对话里没有的地点、物品、事件、别人说过的话\n"
        "4. 不许说「在吗」「最近怎么样」「好久没聊了」\n"
        "5. 不许催他回复，不许说想他想到难受，不许提要求\n"
        "6. 不要解释你为什么突然说话\n"
        "7. 只输出那几句话，不要引号、不要旁白"
    )
    user_prompt = ("情况：%s\n最近聊的：\n%s\n你记得的：\n%s\n\n"
                   "（只用上面出现过的信息；没有具体的东西就说得笼统。你现在想说的是：）") % (
        kind, recent or "（还没聊过）", mem_txt or "（没有）")

    buf = []
    try:
        for delta, _u in client.stream_chat(
                [{"role": "system", "content": sys_prompt},
                 {"role": "user", "content": user_prompt}],
                temperature=0.9, max_tokens=160, model="deepseek-flash",
                extra_body={"thinking": {"type": "disabled"}}):
            if delta:
                buf.append(delta)
    except Exception as e:
        print("[主动] 生成失败：%s" % e, flush=True)
        return ""
    text = "".join(buf).strip().strip('"').strip("「」")
    return text[:120]


# ---------- 主流程 ----------

def candidates(limit: int = 50):
    """找出可能该发的人。"""
    conn = _conn()
    rows = conn.execute("""
        SELECT m.user_id, m.persona, MAX(m.created_at) AS last_at
        FROM messages m
        GROUP BY m.user_id, m.persona
        HAVING last_at >= date('now','-14 day')
        ORDER BY last_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _stage_of(user_id: str, persona: str) -> str:
    try:
        conn = _conn()
        row = conn.execute(
            "SELECT stage FROM user_characters WHERE user_id=? AND persona=?",
            (user_id, persona),
        ).fetchone()
        conn.close()
        return (row["stage"] if row and row["stage"] else "A")
    except Exception:
        return "A"


def _allowed(user_id: str) -> bool:
    p = prefs_of(user_id)
    if not p["enabled"]:
        return False
    if not _window_ok(p["window"]):
        return False
    if not _freq_ok(user_id, p["freq"]):
        return False
    if in_quiet_hours():
        return False
    if sent_today(user_id):
        return False
    if cooling(user_id):
        return False
    return True


def run_tick(dry_run: bool = False, limit: int = 5, mode: str = "rule") -> list:
    ensure_schema()
    out = []
    for c in candidates():
        uid, persona = c["user_id"], c["persona"]
        stage = _stage_of(uid, persona)
        if not _allowed(uid):
            continue

        use_mode = prefs_of(uid).get("mode") or mode
        if use_mode == "model":
            ok, reason = decide_with_model(uid, persona)
            if not ok:
                continue
            picked = pick_trigger(uid, persona, stage)
            trigger, why = picked if picked else ("model", reason)
        else:
            picked = pick_trigger(uid, persona, stage)
            if not picked:
                continue
            trigger, why = picked
        text = build_message(uid, persona, trigger)
        if not text:
            continue
        out.append({"user_id": uid, "persona": persona, "trigger": trigger, "why": why, "text": text})
        if dry_run:
            if len(out) >= limit:
                break
            continue
        conn = _conn()
        conn.execute(
            "INSERT INTO messages(session_id, user_id, persona, role, content, tokens, source) "
            "VALUES(?,?,?,?,?,?,?)",
            ("proactive", uid, persona, "assistant", text, 0, "proactive"),
        )
        conn.execute(
            "INSERT INTO proactive_log(user_id, persona, trigger, content) VALUES(?,?,?,?)",
            (uid, persona, trigger, text),
        )
        conn.commit()
        conn.close()
        if len(out) >= limit:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--mode", choices=["rule", "model"], default="rule")
    ap.add_argument("--loop", type=int, default=0,
                    help="守护模式：每 N 分钟跑一次（0 = 只跑一次）")
    args = ap.parse_args()
    if args.loop > 0:
        import time
        print("守护模式：每 %d 分钟跑一次（Ctrl+C 退出）" % args.loop, flush=True)
        while True:
            try:
                r = run_tick(dry_run=False, limit=args.limit, mode=args.mode)
                if r:
                    for x in r:
                        print("  [%s] %s → %s" % (x["trigger"], x["persona"], x["text"]), flush=True)
                else:
                    print("  本轮 0 条", flush=True)
            except Exception as e:
                print("  出错：%s" % e, flush=True)
            time.sleep(max(60, args.loop * 60))

    rows = run_tick(dry_run=args.dry_run, limit=args.limit, mode=args.mode)
    print("命中 %d 条%s" % (len(rows), "（dry-run，没写库）" if args.dry_run else ""))
    for r in rows:
        print("  [%s] %s / %s — %s" % (r["trigger"], r["user_id"][:8], r["persona"], r["text"]))


# ---------- 模式二：模型自己决定要不要发 ----------

def decide_with_model(user_id: str, persona: str):
    """让模型判断此刻该不该主动开口。返回 (要不要发, 理由)。"""
    from core import client

    conn = _conn()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE user_id=? AND persona=? "
        "ORDER BY id DESC LIMIT 8",
        (user_id, persona),
    ).fetchall()
    conn.close()
    if not rows:
        return (False, "没聊过")

    lines2 = []
    for r in reversed(rows):
        who = "他" if r["role"] == "user" else "你"
        lines2.append(who + "：" + (r["content"] or "")[:60])

    last = rows[0]["created_at"] or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    hours = 0.0
    try:
        hours = (datetime.now()
                 - datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
    except Exception:
        pass

    prompt = (
        "你在扮演陪他的女孩。判断：现在你要不要主动给他发一句话？\n"
        "如果他刚走开不久、或者刚才聊得正热，就别说；"
        "如果他很久没来、或者到了早上或深夜，可以说一句。\n"
        "一天最多说一次，说多了会烦人。\n"
        "只回答一行：要发 或 不要发，后面跟一个理由，不超过 15 字。\n\n"
        "现在：%s（距上次 %.1f 小时）\n最近：\n%s"
    ) % (now, hours, "\n".join(lines2))

    buf = []
    try:
        for delta, _u in client.stream_chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=60, model="deepseek-flash",
                extra_body={"thinking": {"type": "disabled"}}):
            if delta:
                buf.append(delta)
    except Exception as e:
        return (False, "判断失败:" + str(e)[:30])

    ans = "".join(buf).strip()
    return (ans.startswith("要发"), ans[:40])


# ---------- 用户偏好 ----------

def prefs_of(user_id: str) -> dict:
    """读这个人的主动消息设置。默认：开、任意时段、一天一条。"""
    try:
        conn = _conn()
        row = conn.execute(
            "SELECT COALESCE(proactive_enabled,1) e, "
            "COALESCE(proactive_window,'any') w, "
            "COALESCE(proactive_freq,1) f, "
            "COALESCE(proactive_mode,'model') mo FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        conn.close()
        if not row:
            return {"enabled": True, "window": "any", "freq": 1, "mode": "model"}
        return {"enabled": bool(row["e"]), "window": row["w"] or "any",
                "freq": int(row["f"] or 1), "mode": row["mo"] or "model"}
    except Exception:
        return {"enabled": True, "window": "any", "freq": 1, "mode": "model"}


def _window_ok(window: str) -> bool:
    m = _minutes_now()
    if window == "morning":
        return 7 * 60 <= m <= 10 * 60
    if window == "night":
        return 20 * 60 <= m <= QUIET_START
    return True


def _freq_ok(user_id: str, freq: int) -> bool:
    if freq <= 1:
        return True
    conn = _conn()
    row = conn.execute(
        "SELECT sent_at FROM proactive_log WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row or not row["sent_at"]:
        return True
    try:
        last = datetime.strptime(row["sent_at"][:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return True
    return (datetime.now() - last).days >= freq


if __name__ == "__main__":
    main()
