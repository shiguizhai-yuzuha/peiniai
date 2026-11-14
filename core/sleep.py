from datetime import datetime, time
from config import SLEEP_START, SLEEP_END, ENABLE_SLEEP


def parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _in_range(t: time, start: time, end: time) -> bool:
    """支持跨午夜（23:30 → 07:00）。"""
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def is_sleep_time(now: datetime = None) -> bool:
    """全局睡眠（老逻辑，按 config 里的 SLEEP_START / SLEEP_END）。"""
    if not ENABLE_SLEEP:
        return False
    now = now or datetime.now()
    return _in_range(now.time(), parse_time(SLEEP_START), parse_time(SLEEP_END))


def quiet_range(user: dict):
    """取用户的免打扰时段。没设置、或者格式不对 → (None, None)。"""
    s = ((user or {}).get("quiet_start") or "").strip()
    e = ((user or {}).get("quiet_end") or "").strip()
    if not s or not e:
        return (None, None)
    try:
        return (parse_time(s), parse_time(e))
    except Exception:
        return (None, None)


def in_quiet_hours(user: dict, now: datetime = None) -> bool:
    """用户自己设的免打扰时段。

    统一按北京时间，不做时区换算 —— 用户都在国内，做时区只会更乱。
    """
    start, end = quiet_range(user)
    if start is None or end is None:
        return False
    now = now or datetime.now()
    return _in_range(now.time(), start, end)


def quiet_prompt(now: datetime = None) -> str:
    """免打扰时段注入的提示词：她睡着了，被吵醒，回一句就继续睡。"""
    now = now or datetime.now()
    return (
        "## 现在是深夜\n"
        f"现在是 {now.hour:02d}:{now.minute:02d}，你已经睡了，被消息吵醒。\n"
        "说话要短、要含糊，一两句就够，别展开话题。\n"
        "可以抱怨一句被吵醒，但不要生气，也不要赶他走。\n"
        "说完就继续睡——可以留一句「明天再说」。\n"
    )


def minutes_until_sleep(now: datetime = None) -> int:
    """返回距离 SLEEP_START 还有多少分钟。已经入睡返回 -1。"""
    if not ENABLE_SLEEP:
        return -1
    now = now or datetime.now()
    if is_sleep_time(now):
        return -1
    start = parse_time(SLEEP_START)
    target = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if target <= now:
        target = target.replace(day=target.day + 1)
    delta = target - now
    return int(delta.total_seconds() // 60)


def sleep_reply() -> str:
    return "我该睡啦，明天再聊好不好～ 晚安 🌙"
