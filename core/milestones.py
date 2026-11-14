# -*- coding: utf-8 -*-
"""纪念 / 里程碑。

设计原则（很重要，改之前先读）：
- 不弹窗、不算分、不显示进度条。恋爱里没有待办事项，只有"到过哪里"。
- 只在"刚刚发生"的那一轮，作为一句 system 提示出现，让她自然提一句。
- 全部本地计算，不花 token。
"""

from datetime import datetime, timedelta

from db import repository as repo

# key -> 记给她看的一句话
# 视角统一：我 = 她，你 = 玩家。不要出现"他/她"这种性别指向。
DEFS = {
    "first_meet":  "我们第一次说话",
    "first_love":  "你第一次说喜欢我",
    "confessed":   "我们在一起了",
    "name_known":  "我记住了你的名字",
    "seven_days":  "我们聊满了七天",
    "thirty_days": "我们聊满了一个月",
    "streak_3":    "你连着三天来找我",
    "late_night":  "我们第一次在深夜说话",
    "intimacy_50": "我们熟起来了",
    "intimacy_80": "我好像有点不一样了",
}

_LOVE_WORDS = ("喜欢你", "我爱你", "做我女朋友", "做我男朋友", "和我在一起")


def _local(dt_str):
    """库里的 created_at 是 UTC，转成本地时间（+8）。"""
    try:
        return datetime.fromisoformat(str(dt_str)) + timedelta(hours=8)
    except Exception:
        return None


def _streak_end(days, n=3):
    """返回"刚好连满 n 天"那一天的日期字符串；没有就返回 None。"""
    run = 1
    for i in range(1, len(days)):
        try:
            prev = datetime.fromisoformat(days[i - 1]).date()
            cur = datetime.fromisoformat(days[i]).date()
        except Exception:
            run = 1
            continue
        run = run + 1 if (cur - prev).days == 1 else 1
        if run >= n:
            return days[i]
    return None


def check_and_unlock(user_id: str, persona: str):
    """跑一遍判定，返回本轮新解锁的纪念（可能为空列表）。

    每条都会尽量记下"它真正发生的时间"，而不是写库的这一刻。
    只有好感跨坎没有历史曲线可查，只能用当前时间。
    """
    char = repo.get_character_state(user_id, persona)
    msgs = repo.get_all_messages(user_id, persona)
    if not msgs:
        return []

    intimacy = char.get("intimacy") or 0
    have = {m["key"] for m in repo.get_milestones(user_id, persona)}
    new = []

    # 每个日期最早的一条消息时间，用来给"第 N 天"这类纪念定时间
    day_first = {}
    for m in msgs:
        d = str(m["created_at"])[:10]
        day_first.setdefault(d, m["created_at"])
    days = sorted(day_first)

    def add(key, when=None):
        if key in have:
            return
        title = DEFS.get(key)
        if not title:
            return
        if repo.add_milestone(user_id, persona, key, title, when):
            have.add(key)
            new.append({"key": key, "title": title, "at": when})

    add("first_meet", msgs[0]["created_at"])

    # 天数
    if len(days) >= 7:
        add("seven_days", day_first[days[6]])
    if len(days) >= 30:
        add("thirty_days", day_first[days[29]])
    streak_day = _streak_end(days, 3)
    if streak_day:
        add("streak_3", day_first[streak_day])

    # 深夜（本地时间 23:00 之后、凌晨 3 点之前）
    for m in msgs:
        d = _local(m["created_at"])
        if d and (d.hour >= 23 or d.hour < 3):
            add("late_night", m["created_at"])
            break

    # 她记住了名字（先找这个角色自己的，再找跨角色共享的那条）
    for mem in repo.get_all_memories(user_id):
        if mem.get("key") == "name" and mem.get("persona") in (persona, "__global__"):
            add("name_known", mem.get("updated_at"))
            break

    # 确认关系
    if char.get("confessed_at"):
        add("confessed", char["confessed_at"])

    # 第一次说喜欢
    for m in msgs:
        if m["role"] == "user" and any(w in (m["content"] or "") for w in _LOVE_WORDS):
            add("first_love", m["created_at"])
            break

    # 好感跨坎（没有历史曲线，只能记成现在）
    if intimacy >= 50:
        add("intimacy_50")
    if intimacy >= 80:
        add("intimacy_80")

    return new


def sync_dates(user_id: str, persona: str) -> int:
    """把已经记下的纪念，时间改成"它真正发生的那天"。

    用于给早期补录（时间都变成写库当天）的行纠偏。返回更新的行数。
    好感跨坎没法还原，保持原样。
    """
    from db.database import get_conn

    char = repo.get_character_state(user_id, persona)
    msgs = repo.get_all_messages(user_id, persona)
    if not msgs:
        return 0

    day_first = {}
    for m in msgs:
        day_first.setdefault(str(m["created_at"])[:10], m["created_at"])
    days = sorted(day_first)

    when = {"first_meet": msgs[0]["created_at"]}
    if len(days) >= 7:
        when["seven_days"] = day_first[days[6]]
    if len(days) >= 30:
        when["thirty_days"] = day_first[days[29]]
    streak_day = _streak_end(days, 3)
    if streak_day:
        when["streak_3"] = day_first[streak_day]
    for m in msgs:
        d = _local(m["created_at"])
        if d and (d.hour >= 23 or d.hour < 3):
            when["late_night"] = m["created_at"]
            break
    for mem in repo.get_all_memories(user_id):
        if mem.get("key") == "name" and mem.get("persona") in (persona, "__global__"):
            when["name_known"] = mem.get("updated_at")
            break
    if char.get("confessed_at"):
        when["confessed"] = char["confessed_at"]
    for m in msgs:
        if m["role"] == "user" and any(w in (m["content"] or "") for w in _LOVE_WORDS):
            when["first_love"] = m["created_at"]
            break

    conn = get_conn()
    cur = conn.cursor()
    changed = 0
    for m in repo.get_milestones(user_id, persona):
        key = m["key"]
        if key in when and when[key]:
            cur.execute(
                "UPDATE milestones SET unlocked_at=? "
                "WHERE user_id=? AND persona=? AND key=?",
                (when[key], user_id, persona, key),
            )
            changed += cur.rowcount
    conn.commit()
    conn.close()
    return changed


def build_prompt(new_items) -> str:
    """把"刚刚落下的纪念"变成一段 system 提示。"""
    if not new_items:
        return ""
    # 一次补记太多（老用户第一次跑，或者隔了很久才更新）就先不打扰，
    # 免得她一口气念一串"第一次"，反而假。
    if len(new_items) > 3:
        return ""
    lines = "\n".join(f"- {x['title']}" for x in new_items)
    return (
        "## 刚刚落下的东西\n"
        "下面这些，是你们之间刚刚发生的第一次：\n"
        f"{lines}\n"
        "如果这一轮聊到相关的地方，可以顺口提一句，像自己想起来一样。\n"
        "不要宣布，不要说「恭喜」「解锁」「成就」，不要一条一条念出来，"
        "也不要说「今天是第几天」这种话。"
    )
