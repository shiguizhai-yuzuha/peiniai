# -*- coding: utf-8 -*-
"""承诺：他说要做的事，到期了有没有做到

这里不需要模型——纯规则。

窗口怎么算：
  承诺建于 T0，明天到期（T1）
  用户下次来是 T2（T2 > T1）
  检查 T0 ~ T1 之间他有没有发过消息
    有   → 兑现
    没有 → 放鸽子

为什么不能"看现在有没有来"：
  因为放鸽子的人根本不来，结算永远不会被触发。
  所以必须回头看他"应该来的那段时间"来过没有。
"""

from db import repository as repo
from core import events


def make_promise(user_id, persona, what, due_days=1):
    """记一个承诺。due_days=1 表示明天到期。"""
    from datetime import datetime, timedelta
    try:
        due = (datetime.utcnow() + timedelta(days=due_days)).strftime("%Y-%m-%d %H:%M:%S")
        pid = repo.add_promise(user_id, persona, what, due)
        print("[承诺] %s 记下了：%s" % (persona, what), flush=True)
        return pid
    except Exception as ex:
        print("[承诺] 记录失败：%s" % ex, flush=True)
        return None


def _had_message_between(user_id, persona, t0, t1):
    """T0 到 T1 之间，他有没有说过话。"""
    try:
        conn = repo.get_conn()
        n = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id=? AND persona=? "
            "AND role='user' AND created_at > ? AND created_at <= ?",
            (user_id, persona, t0, t1),
        ).fetchone()[0]
        conn.close()
        return n > 0
    except Exception as e:
        print("[承诺] 查消息失败：%s" % e, flush=True)
        return True  # 查不出来就当兑现，不要误伤


def settle_due(user_id, persona):
    """结算所有到期未兑现的承诺。返回结算了几条。"""
    rows = repo.get_due_promises(user_id, persona)
    if not rows:
        return 0

    n = 0
    for p in rows:
        what = p.get("what") or "他说过的事"
        kept = _had_message_between(user_id, persona, p.get("created_at"), p.get("due_at"))

        if kept:
            events.apply(user_id, persona, "兑现", 1, summary=what)
            repo.resolve_promise(p["id"], "kept")
            print("[承诺] ✅ 兑现：%s" % what, flush=True)
        else:
            events.apply(user_id, persona, "放鸽子", 1, summary=what)
            repo.resolve_promise(p["id"], "broken")
            print("[承诺] ✗ 放鸽子：%s" % what, flush=True)
        n += 1

    return n


def open_lines(user_id, persona):
    """还没到期的承诺，给提示词用。"""
    try:
        rows = repo.get_open_promises(user_id, persona)
        if not rows:
            return ""
        return "\n".join("- %s" % (r.get("what") or "") for r in rows)
    except Exception:
        return ""
