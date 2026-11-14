# -*- coding: utf-8 -*-
"""日节奏 —— 情绪与精力的时间函数

这个文件不读库、不写库、不联网。只有纯函数。
所以它可以单独测，也可以被别的地方复用。

模型：两层
    上限/基线     只看几点（CEIL / BASE 两张表，线性插值）
    当前值        由事件加减，自己慢慢回归

    真实精力 = min( CEIL(几点), 当前值 )
    真实情绪 = BASE(几点) + 偏移（偏移按半衰期衰减）
"""

import math
from datetime import datetime

# ============================================================
# 一、精力上限：这个点她最多能有多少劲
# ============================================================
# 索引 = 小时。凌晨最低，上午最高，午后一个低谷，入夜再降。
CEIL = [
    0.12, 0.10, 0.08, 0.08, 0.10, 0.18,   # 00-05  深夜
    0.35, 0.55, 0.72, 0.85, 0.92, 0.92,   # 06-11  起床 → 精神最好
    0.86, 0.72, 0.60, 0.66, 0.78, 0.86,   # 12-17  午后低谷
    0.84, 0.72, 0.55, 0.38, 0.26, 0.18,   # 18-23  放松 → 困
]

# ============================================================
# 二、情绪基线：这个点她本来就有的心情
# ============================================================
BASE = [
     0.00, -0.05, -0.10, -0.12, -0.10, -0.02,   # 00-05
     0.02,  0.06,  0.08,  0.06,  0.04,  0.04,   # 06-11
     0.02,  0.00, -0.02,  0.00,  0.04,  0.08,   # 12-17
     0.10,  0.08,  0.06,  0.04,  0.02,  0.00,   # 18-23
]

# 情绪偏移的半衰期（小时）。
# 30 分钟太短了：下午两点被夸一句，两点半就没了，人不是这样的。
# 改成 2 小时——一次开心能撑过一个下午。
MOOD_HALF_LIFE_H = 2.0

# 精力恢复速度（每小时）。
# 0.15 太快，玩游戏的消耗 20 分钟就被抹平。
# 改成 0.055：一小时恢复 5.5%，玩一局扣 15%，要三小时才补回来。
ENERGY_REGEN = 0.055
# 凌晨恢复更慢
ENERGY_REGEN_NIGHT_FACTOR = 0.45


# ============================================================
# 三、工具
# ============================================================

def _clamp(v, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def _interp(table, hour):
    """按小时在表里线性插值。hour 可以是 13.4 这样的小数。"""
    h = float(hour) % 24.0
    i = int(math.floor(h))
    frac = h - i
    a = table[i % 24]
    b = table[(i + 1) % 24]
    return a + (b - a) * frac


def energy_ceiling(hour=None):
    """这个点她精力的上限（0~1）。"""
    if hour is None:
        hour = datetime.now().hour + datetime.now().minute / 60.0
    return _clamp(_interp(CEIL, hour), 0.0, 1.0)


def mood_base(hour=None):
    """这个点她情绪的基线（-1~1）。"""
    if hour is None:
        hour = datetime.now().hour + datetime.now().minute / 60.0
    return _clamp(_interp(BASE, hour), -1.0, 1.0)


def is_night(hour=None):
    if hour is None:
        hour = datetime.now().hour
    return hour < 6 or hour >= 23


# ============================================================
# 四、结算：把"上次的值"推到"现在"
# ============================================================

def settle_energy(value, last_at, now=None, cap=1.0):
    """精力随时回归：按流逝时间恢复，但不超过这个点的上限。

    value    上次存下的当前值（0~1）
    last_at  上次结算时间（datetime 或 None）
    now      现在（默认 datetime.now()）
    cap      这个人的体力上限（user_characters.energy 那列，默认 1.0）

    返回 (新的当前值, 新的上限)
    """
    if now is None:
        now = datetime.now()

    cur = _clamp(value if value is not None else 1.0, 0.0, 1.0)
    ceil_now = _clamp(energy_ceiling(now.hour + now.minute / 60.0) * _clamp(cap, 0.1, 2.0), 0.0, 1.0)

    if last_at is None:
        # 第一次：直接贴到上限的 80%，不让她一上线就满血
        return round(min(ceil_now, 0.8), 3), round(ceil_now, 3)

    try:
        gap_h = max(0.0, (now - last_at).total_seconds() / 3600.0)
    except Exception:
        gap_h = 0.0

    rate = ENERGY_REGEN * (ENERGY_REGEN_NIGHT_FACTOR if is_night(now.hour) else 1.0)
    cur = cur + rate * gap_h
    cur = min(cur, ceil_now)          # 恢复不能超过此刻的天花板
    return round(cur, 3), round(ceil_now, 3)


def spend_energy(value, amount):
    """做了一件事，扣精力。返回扣完的值。"""
    cur = _clamp(value if value is not None else 1.0, 0.0, 1.0)
    return round(max(0.0, cur - abs(float(amount))), 3)


def settle_mood(offset, last_at, now=None):
    """情绪偏移按半衰期衰减。返回衰减后的偏移（-1~1）。

    注意：这里返回的是"偏移量"，不是最终情绪。
    最终情绪 = mood_base(现在) + 这个偏移。
    """
    off = _clamp(offset if offset is not None else 0.0, -1.0, 1.0)
    if last_at is None or now is None:
        return round(off, 3)
    try:
        gap_h = max(0.0, (now - last_at).total_seconds() / 3600.0)
    except Exception:
        return round(off, 3)
    k = math.pow(0.5, gap_h / MOOD_HALF_LIFE_H)
    return round(off * k, 3)


def mood_now(offset, last_at=None, now=None):
    """算出现在真实的情绪值（-1~1）。"""
    if now is None:
        now = datetime.now()
    off = settle_mood(offset, last_at, now)
    return round(_clamp(mood_base(now.hour + now.minute / 60.0) + off, -1.0, 1.0), 3)


# ============================================================
# 五、标签（给界面用）
# ============================================================

def energy_label(v):
    v = _clamp(v, 0, 1)
    if v >= 0.72:
        return "足"
    if v >= 0.42:
        return "一般"
    if v >= 0.18:
        return "低"
    return "很困"


def mood_label(v):
    """情绪值 → 人话。和 tone.state_of 的分档对齐。"""
    v = _clamp(v, -1, 1)
    if v >= 0.22:
        return "高兴"
    if v <= -0.50:
        return "生气"
    if v <= -0.20:
        return "低落"
    if v <= -0.08:
        return "有点低"
    return "平静"


def table():
    """给调试用：打印一天 24 小时的上限和基线。"""
    rows = []
    for h in range(24):
        rows.append((h, energy_ceiling(h), mood_base(h)))
    return rows
