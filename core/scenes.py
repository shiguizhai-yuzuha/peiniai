# -*- coding: utf-8 -*-
"""场景注册表

加一个新场景，只要在这里加一条 SCENES 条目 + 放一份前端文件。
不用改 app.py，也不用改 UI。

每个场景长这样：
    "beach": {
        "name":      显示名
        "path":      前端入口（static/ 下的相对路径）
        "desc":      一句话
        "phases":    按小时分段的开场（看几点来）
        "actions":   前端发来的动作 → 对四维的影响
        "lines":     台词（预写，不调模型）
    }

这是纯数据和纯逻辑：不读库、不联网。
写库由 caller 拿返回的 effects 去做。
"""

import random
from datetime import datetime

# ============================================================
# 注册表
# ============================================================

SCENES = {

    # --------------------------------------------------------
    "beach": {
        "name": "海边",
        "path": "ocean/index.html",
        "desc": "她已经在那儿了。你来的时候，她没回头。",

        # 按小时的开场（左闭右开）
        "phases": [
            {"from": 0,  "to": 6,  "key": "night",   "doing": "坐在沙上，脚埋进去，涨潮的声音很大"},
            {"from": 6,  "to": 12, "key": "morning", "doing": "在浅水里踩着走，裤脚湿了"},
            {"from": 12, "to": 17, "key": "noon",    "doing": "躺着，晒得暖暖的，有点懒"},
            {"from": 17, "to": 20, "key": "dusk",    "doing": "背对着天，在看日落"},
            {"from": 20, "to": 24, "key": "late",    "doing": "只有星星，声音很小"},
        ],

        # 动作 → 影响
        # mood   : 情绪偏移（-1~1 的增量）
        # energy : 精力消耗（正数是消耗）
        # event  : 触发一个已注册的事件（core/events.py 里的 EVENTS 键）
        "actions": {
            "jellyfish":  {"mood": 0.015, "energy": 0.004},
            "shell":      {"mood": 0.04,  "energy": 0.006},
            "shell_all":  {"mood": 0.22,  "energy": 0.02, "event": "海边_找齐贝壳"},
            "sunset":     {"mood": 0.05,  "energy": 0.03,  "event": ""},
            "water":      {"mood": 0.02,  "energy": 0.01},
            "bottle":     {"mood": 0.18,  "energy": 0.01,  "event": "海边_找到瓶子"},
            "idle_10m":   {"mood": 0.03,  "energy": 0.05},
            "leave":      {"mood": 0.02,  "energy": 0.01},

            # 四个预写的"你对她说的话"（不调模型）
            "ask_cold":   {"mood": 0.03,  "energy": 0.002},
            "ask_stay":   {"mood": 0.07,  "energy": 0.002},
            "ask_watch":  {"mood": 0.05,  "energy": 0.002},
            "ask_leave":  {"mood": 0.02,  "energy": 0.002},
        },

        # 台词（预写）
        "lines": {
            "enter": [
                "……你来了。",
                "（往旁边挪了挪，给你让出一块沙）",
                "（没回头，只是把脚往沙里埋得更深一点）",
            ],
            "enter_low_energy": [
                "（点了点头）",
                "嗯。",
            ],
            "jellyfish": [
                "这个会发光。你别戳它。",
                "（水母慢慢飘过去）……它不怕你。",
                "碰一下就跑，跟你一样。",
                "（她伸手，指尖碰了一下）凉的。",
            ],
            "shell": [
                "这个你留着。",
                "（她把贝壳翻过来）里面还有一点海的声音。",
                "嗯。又一个。",
            ],
            "shell_all": [
                "……你居然都找到了。",
                "（她看了你一会儿）我藏得挺深的。",
            ],
            "sunset": [
                "（她没说话，只是把下巴放到膝盖上）",
                "快没了。",
                "再等一会儿。",
            ],
            "water": [
                "（她看了你一眼，又看回海面）",
                "别踩太深。",
            ],
            "bottle": [
                "（她愣了一下）……你从哪儿找到的。",
                "这个不该在这儿。",
            ],
            "idle": [
                "（她动了一下，把头发别到耳后）",
                "（海浪退下去，又上来）",
                "（她好像在数什么）",
            ],
            "leave": [
                "路上小心。",
                "……明天还来吗。",
                "（她抬了一下手，没挥）",
            ],

            "ask_cold": [
                "……不冷。",
                "（她把外套往肩上拉了拉）一点点。",
                "风一停就不冷了。",
            ],
            "ask_stay": [
                "（她往旁边挪了挪，没说话）",
                "嗯。",
                "……你坐这儿吧。",
            ],
            "ask_watch": [
                "那边。刚才有个东西跳了一下。",
                "水。一直都在动。",
                "（她抬了抬下巴）你看那个。",
            ],
            "ask_leave": [
                "……嗯。",
                "（她没回头）走吧。",
                "路上小心。明天……算了。",
            ],
        },
    },

    # --------------------------------------------------------
    "rose": {
        "name": "粒子玫瑰",
        "path": "rose/index.html",
        "desc": "一束会呼吸的粒子玫瑰。",
        "phases": [
            {"from": 0, "to": 24, "key": "any", "doing": "花在暗处慢慢开"},
        ],
        "actions": {"enter_ok": {"mood": 0.02, "energy": 0.0}},
        "lines": {"enter": ["……"], "idle": ["……"]},
    },

    # --------------------------------------------------------
    # 以后加场景就往下排，格式照抄 beach。
    # 例如：
    # "shop": {
    #     "name": "旧货店",
    #     "path": "shop/index.html",
    #     ...
    # },
    # --------------------------------------------------------
}


# ============================================================
# 查询
# ============================================================

def list_scenes():
    """给 UI 用的场景列表。"""
    return [
        {"key": k, "name": v.get("name", k),
         "desc": v.get("desc", ""), "path": v.get("path", "")}
        for k, v in SCENES.items()
    ]


def get(key):
    return SCENES.get(key)


def phase_of(key, hour=None):
    """这个点来的时候，她在做什么。"""
    sc = SCENES.get(key)
    if not sc:
        return None
    h = datetime.now().hour if hour is None else int(hour) % 24
    for p in sc.get("phases", []):
        if p["from"] <= h < p["to"]:
            return p
    return (sc.get("phases") or [None])[0]


def entrance(key, energy=None, first_time=False, hour=None):
    """进场时她说的一句（以及她在做什么）。"""
    sc = SCENES.get(key)
    if not sc:
        return {"line": "", "doing": ""}

    ph = phase_of(key, hour) or {}
    lines = sc.get("lines", {})

    pool = lines.get("enter") or [""]
    if energy is not None and energy < 0.25:
        low = lines.get("enter_low_energy")
        if low:
            pool = low
    if first_time and lines.get("enter"):
        pool = lines["enter"][:1]

    return {
        "line": random.choice(pool) if pool else "",
        "doing": ph.get("doing", ""),
        "phase": ph.get("key", ""),
    }


def line(key, kind, energy=None):
    """随机取一句预写台词。"""
    sc = SCENES.get(key) or {}
    lines = sc.get("lines", {})
    pool = lines.get(kind) or lines.get("idle") or [""]
    return random.choice(pool) if pool else ""


# ============================================================
# 动作结算
# ============================================================

def apply_action(key, action, energy=None):
    """前端发来一个动作，返回它该造成的效果。

    返回：
        {"ok":bool, "mood":float, "energy_cost":float,
         "event":str, "line":str, "reason":str}

    这个函数不改库。改库由 caller 做。
    """
    out = {"ok": False, "mood": 0.0, "energy_cost": 0.0,
           "event": "", "line": "", "reason": ""}

    sc = SCENES.get(key)
    if not sc:
        out["reason"] = "未知场景"
        return out

    cfg = (sc.get("actions") or {}).get(action)
    if not cfg:
        out["reason"] = "未知动作"
        return out

    # 精力太低的时候，玩不动
    if energy is not None and energy < 0.12 and action not in ("leave", "idle_10m"):
        out["reason"] = "她太累了"
        out["line"] = line(key, "enter_low_energy", energy) or "……"
        return out

    out["ok"] = True
    out["mood"] = float(cfg.get("mood") or 0.0)
    out["energy_cost"] = float(cfg.get("energy") or 0.0)
    out["event"] = cfg.get("event") or ""
    out["line"] = line(key, action, energy)
    return out
