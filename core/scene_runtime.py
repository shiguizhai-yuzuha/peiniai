# -*- coding: utf-8 -*-
"""场景运行时 —— 把 core/scenes.py 的结算落进库

app.py 只调这里，不直接碰库。
"""
from datetime import datetime

from core import scenes, rhythm, events
from db import repository as repo
from db.database import get_conn


def _now():
    return datetime.now()


def _parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except Exception:
        return None


def state_of(user_id, persona):
    """读出"现在"的精力与情绪（已经按时间结算过）。"""
    energy, energy_at, mood, mood_at = None, None, None, None
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT energy_now, energy_at, emotion_score, emotion_at, energy "
            "FROM user_characters WHERE user_id=? AND persona=?",
            (user_id, persona)).fetchone()
        conn.close()
        if row:
            energy = row["energy_now"]
            energy_at = _parse_ts(row["energy_at"])
            mood = row["emotion_score"]
            mood_at = _parse_ts(row["emotion_at"])
            cap = float(row["energy"] or 1.0)
        else:
            cap = 1.0
    except Exception as e:
        print("[场景] 读状态失败：%s" % e, flush=True)
        cap = 1.0

    e_now, ceil = rhythm.settle_energy(
        energy if energy is not None else 0.8, energy_at, _now(), cap=cap)

    # 库里 emotion_score 存的是"偏移量"，显示值 = 基线 + 偏移。
    # 这两个必须分开返回，否则会把绝对值写回偏移量，越写越偏。
    off_now = rhythm.settle_mood(mood or 0.0, mood_at, _now())
    m_now = rhythm.mood_now(mood or 0.0, mood_at, _now())

    return {
        "energy": e_now,
        "energy_ceiling": ceil,
        "mood": m_now,            # 显示用（-1~1 的真实情绪）
        "mood_offset": off_now,   # 写回库用（偏移量）
        "energy_label": rhythm.energy_label(e_now),
        "mood_label": rhythm.mood_label(m_now),
    }


def entrance(user_id, persona, key, first_time=False):
    """进场：结算状态 + 给她一句开场。"""
    st = state_of(user_id, persona)
    ent = scenes.entrance(key, energy=st["energy"], first_time=first_time)
    return dict(ent, state=st)


def act(user_id, persona, key, action):
    """前端发来一个动作：结算 + 落库 + 回一句台词。"""
    st = state_of(user_id, persona)

    # 精力回写（懒结算）
    try:
        repo.update_character_energy(user_id, persona, st["energy"])
    except Exception as e:
        print("[场景] 写精力失败：%s" % e, flush=True)

    res = scenes.apply_action(key, action, energy=st["energy"])
    if not res.get("ok"):
        return {"ok": False, "line": res.get("line", ""), "reason": res.get("reason", ""), "state": st}

    # 情绪：在"衰减后的偏移量"上加减，写回偏移量（不是绝对值）
    new_mood = max(-1.0, min(1.0, st.get("mood_offset", 0.0) + float(res["mood"] or 0)))
    try:
        repo.update_character_emotion(user_id, persona, new_mood)
        conn = get_conn()
        conn.execute(
            "UPDATE user_characters SET emotion_at=? "
            "WHERE user_id=? AND persona=?",
            (_now().strftime("%Y-%m-%d %H:%M:%S"), user_id, persona))
        conn.commit(); conn.close()
    except Exception as e:
        print("[场景] 写情绪失败：%s" % e, flush=True)

    # 精力消耗
    if res.get("energy_cost"):
        try:
            repo.update_character_energy(
                user_id, persona,
                rhythm.spend_energy(st["energy"], res["energy_cost"]))
        except Exception as e:
            print("[场景] 扣精力失败：%s" % e, flush=True)

    # 触发事件（礼物、里程碑之类）
    ev = (res.get("event") or "").strip()
    if ev:
        try:
            events.apply(user_id, persona, ev, intensity=1, summary="海边")
        except Exception as e:
            print("[场景] 事件失败：%s" % e, flush=True)

    st2 = state_of(user_id, persona)
    return {
        "ok": True,
        "line": res.get("line", ""),
        "event": ev,
        "state": st2,
    }
