# -*- coding: utf-8 -*-
"""四向状态环 —— 好感 / 信任 / 情绪 / 精力

蓝色 + 海浪：
    · 外圈一条正弦波浪环，缓慢旋转（海面）
    · 每条弧的末端有一个浪头小点，轻轻起伏
    · 弧本身是那条"水位"的轨迹

这四个值就是 core/tone.py 里 decide() 的四个入参。
环上四段 → 合成中心那个状态 → 那个状态决定她这一轮怎么说话。

只读，不写库。
"""
import math
from datetime import datetime

from core import tone
from db.database import get_conn

# ---------------------------------------------------------------- 几何

CENTER = 66.0
RADIUS = 48.0
GAP = 8.0
SPAN = 90.0

SEGMENTS = ("love", "trust", "mood", "energy")

NAME = {
    "love": "好感",
    "trust": "信任",
    "mood": "情绪",
    "energy": "精力",
}


def _point(cx, cy, r, deg):
    rad = math.radians(deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _arc_path(i):
    a0 = -90 + i * SPAN + GAP / 2
    a1 = -90 + (i + 1) * SPAN - GAP / 2
    x0, y0 = _point(CENTER, CENTER, RADIUS, a0)
    x1, y1 = _point(CENTER, CENTER, RADIUS, a1)
    return "M %.2f %.2f A %.2f %.2f 0 0 1 %.2f %.2f" % (
        x0, y0, RADIUS, RADIUS, x1, y1)


def _tip(i, frac):
    """第 i 段填充到 frac 时，浪头所在的坐标。"""
    a0 = -90 + i * SPAN + GAP / 2
    a1 = -90 + (i + 1) * SPAN - GAP / 2
    a = a0 + max(0.0, min(1.0, frac)) * (a1 - a0)
    return _point(CENTER, CENTER, RADIUS, a)


def _wave_circle(r_base, amp=1.6, freq=9, points=160, phase=0.0):
    """一圈正弦起伏的闭合路径，用来看成海面。"""
    d = []
    for k in range(points + 1):
        th = 2.0 * math.pi * k / points
        r = r_base + amp * math.sin(freq * th + phase)
        x = CENTER + r * math.cos(th - math.pi / 2)
        y = CENTER + r * math.sin(th - math.pi / 2)
        d.append(("%.2f" % x) + " " + ("%.2f" % y))
    return "M " + d[0] + " L " + " L ".join(d[1:])


def _clamp01(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------- 取值

def _energy_label(e):
    if e >= 0.72:
        return "足"
    if e >= 0.42:
        return "一般"
    return "低"


def _mood_label(state):
    if state == "烦躁":
        return "烦躁"
    if state == "消沉":
        return "消沉"
    if state == "活泼":
        return "高兴"
    if state == "温和":
        return "不错"
    if state == "疲惫":
        return "困"
    return "平静"


def build(user_id, persona):
    intimacy, trust, mood, cap = 0.0, 20.0, 0.0, 1.0
    mem_n = 0
    energy_now = None

    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT intimacy, trust, emotion_score, energy, confessed_at "
            "FROM user_characters WHERE user_id=? AND persona=?",
            (user_id, persona)).fetchone()
        if row:
            intimacy = float(row["intimacy"] or 0)
            trust = float(row["trust"] or 20)
            mood = float(row["emotion_score"] or 0)
            cap = float(row["energy"] or 1.0)
        mrow = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id=? AND persona=?",
            (user_id, persona)).fetchone()
        mem_n = int(mrow[0]) if mrow else 0
        conn.close()
    except Exception as e:
        print("[环] 读库失败：%s" % e, flush=True)

    # 情绪与精力走 rhythm 结算（按真实时间流逝），不再是"原始值 × 时间函数"
    try:
        from core import scene_runtime as _rt
        _st = _rt.state_of(user_id, persona)
        energy_now = _st["energy"]
        mood = _st["mood"]
    except Exception as e:
        print("[环] 节奏结算失败，退回默认：%s" % e, flush=True)

    if energy_now is None:
        energy_now = tone.energy_by_hour(datetime.now().hour) * cap

    t = tone.decide(intimacy=intimacy, trust=trust, mood=mood, energy=energy_now)

    return {
        "love": {
            "name": NAME["love"], "label": t["stage"],
            "frac": _clamp01(intimacy / 100.0),
            "tip": "好感 %.0f · %s" % (intimacy, t["stage"]),
        },
        "trust": {
            "name": NAME["trust"], "label": t["trust"],
            "frac": _clamp01(trust / 100.0),
            "tip": "信任 %.0f · %s" % (trust, t["trust"]),
        },
        "mood": {
            "name": NAME["mood"], "label": _mood_label(t["state"]),
            "frac": _clamp01((mood + 1.0) / 2.0),
            "tip": "情绪 %+.2f · %s" % (mood, _mood_label(t["state"])),
        },
        "energy": {
            "name": NAME["energy"], "label": _energy_label(energy_now),
            "frac": _clamp01(energy_now),
            "tip": "精力 %.2f · %s" % (energy_now, _energy_label(energy_now)),
        },
        "_center": {"state": t["state"], "stage": t["stage"], "mode": t["mode"]},
        "_mem": mem_n,
    }


def render(user_id, persona):
    if not user_id:
        return ""

    st = build(user_id, persona)
    center = st["_center"]

    arcs = []
    drops = []
    for i, key in enumerate(SEGMENTS):
        d = st[key]
        frac = d["frac"]
        off = round(100.0 - frac * 100.0, 2)
        path = _arc_path(i)

        arcs.append(
            '<g class="ringseg"><title>%s</title>'
            '<path class="ring-track" d="%s"/>'
            '<path class="ring-fill" d="%s" pathLength="100" '
            'stroke-dasharray="100 100" stroke-dashoffset="%s"/>'
            '</g>' % (d["tip"], path, path, off)
        )

        # 浪头：只在有进度时出现
        if frac > 0.02:
            tx, ty = _tip(i, frac)
            drops.append(
                '<circle class="drop d%d" cx="%.2f" cy="%.2f" r="%.2f" '
                'style="--dl:%.2fs"/>' % (i, tx, ty, 2.4 + frac * 1.4, i * 0.45)
            )

    bars = "".join(
        '<div class="ringbar">'
        '<span>%s</span>'
        '<span class="bt"><i class="bf" style="width:%.0f%%"></i></span>'
        '<span class="bv">%s</span>'
        '</div>' % (st[k]["name"], st[k]["frac"] * 100.0, st[k]["label"])
        for k in SEGMENTS
    )

    wave1 = _wave_circle(RADIUS + 11.0, amp=1.9, freq=9, phase=0.0)
    wave2 = _wave_circle(RADIUS + 14.5, amp=1.3, freq=13, phase=2.1)

    svg = (
        '<svg viewBox="0 0 132 132" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<defs>'
        '<linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#3f9bff"/>'
        '<stop offset="48%" stop-color="#7fd0ff"/>'
        '<stop offset="100%" stop-color="#2a6fd0"/>'
        '</linearGradient>'
        '<radialGradient id="ringHalo" cx="50%" cy="50%" r="50%">'
        '<stop offset="55%" stop-color="rgba(90,170,255,0)"/>'
        '<stop offset="100%" stop-color="rgba(90,170,255,.26)"/>'
        '</radialGradient>'
        '</defs>'

        '<circle cx="66" cy="66" r="62" fill="url(#ringHalo)"/>'

        '<g class="wave w1"><path d="' + wave1 + '"/></g>'
        '<g class="wave w2"><path d="' + wave2 + '"/></g>'

        + "".join(arcs) +
        '<g class="drops">' + "".join(drops) + '</g>'
        '</svg>'
    )

    return (
        '<div class="ringcard">'
        '<div class="ringstage">' + svg +
        '<div class="ringcore">'
        '<span class="cn">' + center["state"] + '</span>'
        '<span class="cs">' + center["stage"] + '</span>'
        '</div>'
        '</div>'
        '<div class="ringbars">' + bars + '</div>'
        '<a class="ringgo" href="/scene/beach?u=' + user_id + '&p=' + persona + '">'
        '去海边</a>'
        '<div class="ringfoot"><span>' + persona + '</span>'
        '<span>记忆 ' + str(st["_mem"]) + ' 条</span></div>'
        '</div>'
    )
