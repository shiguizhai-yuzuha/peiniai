# -*- coding: utf-8 -*-
"""日摘要 —— 跨天的那座桥

问题：上下文窗口只有 16 轮，跨天之后昨天的对话全丢了，
      只剩 key-value 标签（"moment:第一次约定旅游"），说不出过程。

做法：每天第一次说话时，后台把昨天整天的对话压成一段第一人称的日记，
      存进 daily_summaries，第二天注入。

为什么放后台：生成要 3-5 秒，不能让她等。
              第一次没准备好就没准备，不阻塞回复。
"""

import threading
from datetime import datetime, timedelta, timezone

from core.client import client
from config import MODEL
from db import repository as repo

# 昨天至少有这么多条消息才值得写日记。
# 10 条（5 轮）写出来只有一句「他说累，我让他早点睡」，不值得花一次调用。
MIN_MSGS = 15
# 近 7 天至少要聊过这么多天。只聊过一次的临时角色不写——第二天的日记他也不会看。
MIN_ACTIVE_DAYS = 2
# 每天最多写一次
MAX_SUMMARY_CHARS = 320

SUMMARY_PROMPT = """下面是你和他在 {day} 这一天的全部对话。

请你以第一人称，写一段"昨天发生了什么"的日记，给明天的你自己看。

要求：
- 150-250 字，一段，不要分点
- 写具体发生过的事：他说了什么、你做了什么、中间卡在哪儿
- 写他的状态和情绪变化（他累、他绕开话题、他突然说了句实话）
- 写你们之间推进了或者停在哪一步
- 用"他"称呼对方，用"我"称呼你自己
- **不要总结、不要评价、不要写"我们关系更近了"这种话**
- 不要写你无法知道的事

只输出日记正文，不要任何前缀、标题、引号。

【对话】
{dialogue}"""


_today_cache = {}   # (user_id, persona, day) -> True  已经排过任务了
_lock = threading.Lock()


def _bj_today():
    """北京时间的今天（日期对象）"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


def _fetch_day_msgs(user_id, persona, day_str):
    """取某一天（北京时间的日期，形如 2026-10-28）的全部消息"""
    try:
        conn = repo.get_conn()
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE user_id=? AND persona=? "
            "AND DATE(created_at, '+8 hours')=? "
            "ORDER BY id",
            (user_id, persona, day_str),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print("[日记] 读消息失败：%s" % e, flush=True)
        return []


def get(user_id, persona, day_str):
    """取某一天的摘要。没有就返回 None。"""
    try:
        conn = repo.get_conn()
        row = conn.execute(
            "SELECT summary FROM daily_summaries WHERE user_id=? AND persona=? AND day=?",
            (user_id, persona, day_str),
        ).fetchone()
        conn.close()
        return (row[0] if row else None)
    except Exception:
        return None


def recent(user_id, persona, days=2):
    """取最近几天的摘要，返回 [(day, summary), ...]，新的在后。"""
    out = []
    today = _bj_today()
    for i in range(days, 0, -1):
        d = str(today - timedelta(days=i))
        s = get(user_id, persona, d)
        if s:
            out.append((d, s))
    return out


def _write(user_id, persona, day_str, msgs):
    """真的去写摘要。跑在后台线程里。"""
    try:
        dialogue = "\n".join(
            "%s: %s" % ("他" if m.get("role") == "user" else "我",
                        str(m.get("content") or "")[:300])
            for m in msgs
        )
        # 太长就砍掉最前面的（保留最近的）
        if len(dialogue) > 12000:
            dialogue = "……（前面省略）\n" + dialogue[-12000:]

        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user",
                       "content": SUMMARY_PROMPT.format(day=day_str, dialogue=dialogue)}],
            temperature=0.4,
            max_tokens=500,
            timeout=90,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return
        if len(text) > MAX_SUMMARY_CHARS:
            text = text[:MAX_SUMMARY_CHARS]

        conn = repo.get_conn()
        conn.execute(
            "INSERT INTO daily_summaries(user_id, persona, day, summary, msg_count, created_at) "
            "VALUES(?,?,?,?,?,DATETIME('now')) "
            "ON CONFLICT(user_id, persona, day) DO UPDATE SET "
            "summary=excluded.summary, msg_count=excluded.msg_count",
            (user_id, persona, day_str, text, len(msgs)),
        )
        conn.commit()
        conn.close()
        print("[日记] %s / %s / %s 写好了（%d 条对话，%d 字）"
              % (user_id[:8], persona, day_str, len(msgs), len(text)), flush=True)
    except Exception as e:
        print("[日记] 写失败：%s" % e, flush=True)


def _active_days(user_id, persona, days=7):
    """近 N 天里有几天聊过。一次 SQL，不花钱。"""
    try:
        conn = repo.get_conn()
        n = conn.execute(
            "SELECT COUNT(DISTINCT DATE(created_at,'+8 hours')) FROM messages "
            "WHERE user_id=? AND persona=? AND created_at >= DATETIME('now', ?)",
            (user_id, persona, "-%d day" % days),
        ).fetchone()[0]
        conn.close()
        return int(n or 0)
    except Exception:
        return 0


def maybe_build(user_id, persona):
    """如果昨天还没有摘要，起个后台线程去写。

    幂等：同一天同一个角色只会排一次任务。
    不阻塞：调用方立刻返回。
    """
    try:
        y = str(_bj_today() - timedelta(days=1))
        key = (user_id, persona, y)
        with _lock:
            if key in _today_cache:
                return
            _today_cache[key] = True

        if get(user_id, persona, y):
            return

        msgs = _fetch_day_msgs(user_id, persona, y)
        if len(msgs) < MIN_MSGS:
            return

        # 只给真的在聊的角色写。聊过一次的临时角色，第二天的日记他也不会看。
        if _active_days(user_id, persona) < MIN_ACTIVE_DAYS:
            return

        threading.Thread(
            target=_write, args=(user_id, persona, y, msgs),
            daemon=True, name="daily-summary",
        ).start()
    except Exception as e:
        print("[日记] 排队失败：%s" % e, flush=True)
