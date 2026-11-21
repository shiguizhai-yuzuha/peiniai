# -*- coding: utf-8 -*-
"""事件系统：让四维由"发生了什么"驱动

现在四维是按轮数涨的（聊一句信任 +0.3）。
这是第一版：先只认"承诺"这一条，跑通了再复制别的。

设计见 开发日志/事件与关系_设计.md
"""

import json
from datetime import datetime, timedelta

from db import repository as repo


# ============ 事件表 ============
# 一个事件对四维的影响。数值是"强度 1"时的基准，实际按 intensity 乘。
EVENTS = {
    # ---- 承诺相关 ----
    "兑现": {
        "trust": 8,
        "emotion": 10,
        "affection": 3,
        "line": "你真来了。",
    },
    "放鸽子": {
        "trust": -12,
        "emotion": -12,
        "affection": -2,
        "line": "你昨天……忙吗？",
    },
    # ---- 关系里常见的事 ----
    "吵架": {
        "trust": -8,
        "emotion": -15,
        "affection": -4,
    },
    "坦白": {
        "trust": 10,
        "emotion": 12,
        "affection": 4,
    },
    "深夜陪着": {
        "emotion": 6,
        "affection": 2,
    },
    "替她记着": {
        "trust": 5,
        "affection": 2,
    },
    "说了重话": {
        "trust": -10,
        "emotion": -14,
        "affection": -5,
    },
}

# ---- 封顶：不做封顶，事件系统会被刷爆 ----
MAX_PER_EVENT = 15.0     # 单个事件对好感/信任最多改 15
MAX_SAME_TYPE_DAY = 3    # 同一类事件一天最多生效 3 次
MAX_TOTAL_DAY = 25.0     # 一天总影响最多 ±25

# ---- 情绪的单位 ----
# 表里的 emotion 是"人话刻度"（+10 表示明显高兴）。
# 但库里 emotion_score 是 -1 ~ 1（见 core/emotion.py）。
# 所以写库前必须除这个数，否则 +10 会把 -1~1 的值顶到 10，
# 环上 (x+1)/2 一律裁成 1，永远显示"活泼"。
EMOTION_SCALE = 20.0
MAX_EMOTION_EVENT = 1.0  # 单个事件对情绪最多改 ±1.0（满格的一半）


def _today_start():
    """今天 00:00（UTC，跟库里一致）"""
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _same_type_today(user_id, persona, etype):
    conn = repo.get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=? AND persona=? AND type=? AND created_at>=?",
        (user_id, persona, etype, _today_start()),
    ).fetchone()[0]
    conn.close()
    return n


def _total_today(user_id, persona):
    """今天已经用掉的正/负额度，分开算。

    好事和坏事不能共用一份额度——否则今天被夸三次之后，
    就再也不能被扣分了，那不合理。
    """
    conn = repo.get_conn()
    rows = conn.execute(
        "SELECT trust_delta FROM events "
        "WHERE user_id=? AND persona=? AND created_at>=?",
        (user_id, persona, _today_start()),
    ).fetchall()
    conn.close()
    pos = sum(r[0] for r in rows if (r[0] or 0) > 0)
    neg = sum(-r[0] for r in rows if (r[0] or 0) < 0)
    return pos, neg


def _diminish_factor(user_id, persona, etype):
    """这个类型的事件，他做过几次了？返回系数。

    第 1 次 1.0，第 2 次 0.75，第 3 次 0.5，第 4 次起 0.35（下限）。
    """
    try:
        conn = repo.get_conn()
        # 只看最近 30 天。一个月没做的事，再做一次会恢复成新鲜事。
        n = conn.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND persona=? AND type=? "
            "AND created_at >= DATETIME('now','-30 day')",
            (user_id, persona, etype),
        ).fetchone()[0]
        conn.close()
    except Exception:
        return 1.0
    return max(0.35, 1.0 - 0.25 * n)


def _clamp(v, lo=-MAX_PER_EVENT, hi=MAX_PER_EVENT):
    return max(lo, min(hi, v))


def apply(user_id, persona, etype, intensity=1, summary=""):
    """记一个事件，并改四维。

    返回 dict：实际生效了多少，或者为什么没生效。
    不抛异常。
    """
    result = {"ok": False, "type": etype, "reason": "", "affection": 0, "trust": 0, "emotion": 0}
    try:
        cfg = EVENTS.get(etype)
        if not cfg:
            result["reason"] = "未知事件类型"
            return result

        try:
            intensity = max(1, min(3, int(intensity)))
        except Exception:
            intensity = 1

        if _same_type_today(user_id, persona, etype) >= MAX_SAME_TYPE_DAY:
            result["reason"] = "同类事件今天已经 %d 次" % MAX_SAME_TYPE_DAY
            return result

        pos_used, neg_used = _total_today(user_id, persona)

        a = _clamp(float(cfg.get("affection", 0)) * intensity)
        t = _clamp(float(cfg.get("trust", 0)) * intensity)
        # 情绪：先按刻度换算成 -1~1，再单独封顶
        e = float(cfg.get("emotion", 0)) * intensity / EMOTION_SCALE
        e = max(-MAX_EMOTION_EVENT, min(MAX_EMOTION_EVENT, e))

        # 边际递减：同一类事重复做，正面收益越来小。
        # 因为「你天天都来」会从惊喜变成常态，常态不该和第一次一样值钱。
        # 惩罚不递减——做错事每次都一样疼。
        factor = 1.0
        if a > 0 or t > 0 or e > 0:
            factor = _diminish_factor(user_id, persona, etype)
            if a > 0:
                a *= factor
            if t > 0:
                t *= factor
            if e > 0:
                e *= factor

        # 今天还剩多少额度（正负分开）
        used = pos_used if t > 0 else neg_used
        if used >= MAX_TOTAL_DAY:
            result["reason"] = ("今天的正向影响已到上限" if t > 0 else "今天的负向影响已到上限")
            return result
        room = max(0.0, MAX_TOTAL_DAY - used)
        scale = 1.0
        if abs(t) > room and abs(t) > 0:
            scale = room / abs(t)
            a, t, e = a * scale, t * scale, e * scale   # 按同一比例缩，保住相对关系

        # 陪伴模式不涨好感度（事件带来的信任/情绪照旧）
        try:
            from core import mode as _mode
            _companion = _mode.is_companion(user_id, persona)
        except Exception:
            _companion = False

        if a and not _companion:
            repo.update_character_intimacy(user_id, persona, a)
        if t:
            repo.update_character_trust(user_id, persona, t)
        if e:
            # emotion 是设定值不是增量
            try:
                st = repo.get_character_state(user_id, persona) or {}
                cur = float(st.get("emotion_score") or 0)
            except Exception:
                cur = 0.0
            repo.update_character_emotion(user_id, persona, max(-1.0, min(1.0, cur + e)))

        # 长期任务：这件事对某个"任务"有进度
        if cfg.get("quest"):
            _total = repo.add_quest_points(user_id, persona, cfg["quest"],
                                           int(cfg.get("quest_points") or 1))
            result["quest"] = cfg["quest"]
            result["quest_points"] = _total
            print("[任务] %s %s 进度 %d" % (persona, cfg["quest"], _total), flush=True)

        repo.add_event(user_id, persona, etype,
                       summary=summary, intensity=intensity,
                       affection=a, trust=t, emotion=e)

        result.update(ok=True, affection=round(a, 1), trust=round(t, 1), emotion=round(e, 1))
        print("[事件] %s %s×%d → 好%+.1f 信%+.1f 情%+.1f%s"
              % (persona, etype, intensity, a, t, e,
                 ("（额度折算 %.0f%%，重复系数 %.0f%%）" % (scale*100, factor*100)) if (scale < 1 or factor < 1) else ""), flush=True)
        return result
    except Exception as ex:
        result["reason"] = str(ex)
        print("[事件] 失败：%s" % ex, flush=True)
        return result


def line_for(etype):
    """这个事件有没有配一句台词。没有就返回空串。"""
    return (EVENTS.get(etype) or {}).get("line", "")


# ============ 承诺 ============

def make_promise(user_id, persona, what, due_days=1):
    """记一个承诺。转调 core.promises，避免两份实现。"""
    from core import promises as _p
    return _p.make_promise(user_id, persona, what, due_days)


def due_promises(user_id, persona):
    """到点还没兑现的承诺。"""
    try:
        return repo.get_due_promises(user_id, persona)
    except Exception:
        return []


def settle(promise_id, kept):
    """兑现（kept=True）或放鸽子（kept=False）。"""
    try:
        repo.resolve_promise(promise_id, "kept" if kept else "broken")
    except Exception as ex:
        print("[承诺] 结算失败：%s" % ex, flush=True)


# ============ 自然衰减 ============

# 几天不来，信任每天掉一点。不是惩罚，是时间。
DECAY_AFTER_DAYS = 3
DECAY_PER_DAY = 2.0
DECAY_FLOOR = 10.0      # 不会掉到 10 以下——她不会把你忘光


def decay(user_id, persona):
    """他好几天没来，信任慢慢掉。

    只在「他来了」的时候结算一次（懒计算），不跑定时任务。
    返回掉了多少，没掉就是 0。
    """
    try:
        conn = repo.get_conn()
        row = conn.execute(
            "SELECT MAX(created_at) FROM messages WHERE user_id=? AND persona=? AND role='user'",
            (user_id, persona),
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return 0.0

        last = datetime.fromisoformat(str(row[0]))
        gap = (datetime.utcnow() - last).total_seconds() / 86400.0
        if gap <= DECAY_AFTER_DAYS:
            return 0.0

        st = repo.get_character_state(user_id, persona) or {}
        cur = float(st.get("trust") or 0)
        if cur <= DECAY_FLOOR:
            return 0.0

        drop = min(cur - DECAY_FLOOR, DECAY_PER_DAY * (gap - DECAY_AFTER_DAYS))
        if drop <= 0:
            return 0.0

        repo.update_character_trust(user_id, persona, -drop)
        print("[衰减] %s 他 %.0f 天没来，信任 -%.1f" % (persona, gap, drop), flush=True)
        return round(drop, 1)
    except Exception as e:
        print("[衰减] 失败，跳过：%s" % e, flush=True)
        return 0.0
