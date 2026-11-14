"""腔 · 她说话的样子（设置）

用户在 /voice 页面上选的东西，落到这里。

负责
    · 读设置：用户偏好 > config 默认
    · 把「发几条 × 每句多长」翻成一次具体的「这一轮说几条、每条多长」
    · 把两个轴算成 max_tokens

不负责
    · 不生成文字（那是 services/chat）
    · 不做去 AI 味清洗（那是 core/deai）
    · 不碰提示词的人设部分（那是 core/personas）

为什么叫腔
    同一个人，换个腔调就是另一个人。
    这几项设置改的不是她说什么，是她用什么腔调说。
"""

import random

from config import MAX_TOKENS as _CFG_MAX_TOKENS
from config import TEMPERATURE as _CFG_TEMP

DEFAULTS = {
    # 总开关：强化拟人。默认关 —— 关着的时候下面所有设置都不生效，
    # 她按 2026-11-13 之前的方式说话。用户在 /voice 自己打开。
    "enhance": False,
    "rows": "auto",      # few / mid / many / auto（auto = 她自己决定，默认）
    "len": "mid",        # short / mid / long
    "sample": True,      # 说话样本
    "plain": True,       # 说人话
    "terse": False,
    "knows_us": True,   # 记得在一起多久：问天数直接答、不许说"刚认识"
    "knows": True,      # 同一个东西，前端用的名字
    "temp": _CFG_TEMP,   # 温度
    "freq": 0.0,         # frequency_penalty
    "pres": 0.0,         # presence_penalty
    "cap": None,         # max_tokens 手动值；None = 自动
}

# 两个轴 → 回复上限
CAP = {
    "few":  {"short": 60,  "mid": 150, "long": 600},
    "mid":  {"short": 90,  "mid": 200, "long": 700},
    "many": {"short": 200, "mid": 400, "long": 800},
}

# 两个轴 → 这一次说几条的权重
# 值 = (条数, 权重)
_ROWS_W = {
    "few":  [(1, 55), (2, 40), (3, 5)],
    "mid":  [(1, 20), (2, 34), (3, 28), (4, 12), (5, 5), (6, 1)],
    "many": [(1, 8),  (2, 18), (3, 30), (4, 24), (5, 14), (6, 6)],
}

# 「每句多长」→ 追加到提示词的一句约束
_LEN_LINE = {
    "short": "每一句都很短，尽量 15 字以内。像微信里随手发的。",
    "mid":   "每句正常长度，15 到 40 字。别写成段落。",
    "long":  "如果有话要说，可以说长一点，一段话也可以。",
}

# 小作文：少 + 长 时，额外给一句
_ESSAY_LINE = (
    "这一次如果你想认真说一件事，就用一条长消息说完，"
    "不要拆成好几条。"
)

_TIERS = ("很稳", "正常", "活泼", "飘")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def normalize(cfg):
    """把前端来的任意 dict 收成一份干净的设置。"""
    out = dict(DEFAULTS)
    if isinstance(cfg, dict):
        out.update({k: cfg[k] for k in cfg if k in DEFAULTS})

    if out["rows"] not in _ROWS_W and out["rows"] != "auto":
        out["rows"] = "auto"
    if out["len"] not in _LEN_LINE:
        out["len"] = "mid"

    out["sample"] = bool(out["sample"])
    out["plain"] = bool(out["plain"])
    out["terse"] = bool(out["terse"])
    # 前端叫 knows，后端叫 knows_us。两边都认，回给前端时补一个 knows。
    if isinstance(cfg, dict) and "knows" in cfg and "knows_us" not in cfg:
        out["knows_us"] = bool(cfg["knows"])
    out["enhance"] = bool(out.get("enhance", out.get("enhanced", False)))
    out["knows_us"] = bool(out.get("knows_us", True))
    out["knows"] = out["knows_us"]

    try:
        out["temp"] = round(_clamp(float(out["temp"]), 0.5, 1.2), 2)
    except Exception:
        out["temp"] = DEFAULTS["temp"]
    for k in ("freq", "pres"):
        try:
            out[k] = round(_clamp(float(out[k]), 0.0, 0.8), 2)
        except Exception:
            out[k] = 0.0

    cap = out.get("cap")
    if cap in (None, "", "auto", 0):
        out["cap"] = None
    else:
        try:
            out["cap"] = int(_clamp(float(cap), 60, 800))
        except Exception:
            out["cap"] = None

    # 别啰嗦 接管：条数不能多，句子不能长
    if out["terse"]:
        if out["rows"] == "many":
            out["rows"] = "few"
        if out["len"] == "long":
            out["len"] = "mid"

    return out


def load(user_id=None):
    """读一个人的设置。没登录就给默认值。"""
    if not user_id:
        return dict(DEFAULTS)
    try:
        from db import repository as repo
        raw = repo.get_user_pref(user_id, "voice_cfg", "") or ""
        if not raw:
            return dict(DEFAULTS)
        import json
        return normalize(json.loads(raw))
    except Exception:
        return dict(DEFAULTS)


def save(user_id, cfg):
    """存一个人的设置。存失败返回 False，不抛。"""
    if not user_id:
        return False
    try:
        from db import repository as repo
        import json
        repo.set_user_pref(user_id, "voice_cfg", json.dumps(normalize(cfg), ensure_ascii=False))
        return True
    except Exception:
        return False


def cap_of(cfg):
    """这一次的回复上限。手动值优先。"""
    if cfg and cfg.get("cap"):
        return int(cfg["cap"])
    rows = (cfg or {}).get("rows", "auto")
    if rows == "auto":
        rows = "mid"
    ln = (cfg or {}).get("len", "mid")
    return CAP.get(rows, CAP["mid"]).get(ln, 200)


def pick_rows(cfg, state=""):
    """抽这一轮说几条。

    两个轴决定分布，她的状态再微调：
      累、消沉 → 往少里偏
      活泼 → 往多里偏
    """
    rows = (cfg or {}).get("rows", "auto")

    if rows == "auto":
        # 「她自己决定」= 回到 2026-10-31 之前那套算法：
        # 不看用户选的轴，由她的状态（活泼/疲惫/消沉）加权随机抽条数。
        # 这不是"让模型自己说几条"——那个方案试过，74% 都是三段。
        try:
            from core import tone as _tone
            return _tone.pick_reply_len(state or "")
        except Exception:
            rows = "mid"

    table = list(_ROWS_W.get(rows, _ROWS_W["mid"]))

    if state in ("疲惫", "消沉", "烦躁"):
        table = [(n, w * (1.6 if n <= 2 else 0.5)) for n, w in table]
    elif state == "活泼":
        table = [(n, w * (0.6 if n <= 2 else 1.5)) for n, w in table]

    ks = [n for n, _ in table]
    ws = [w for _, w in table]
    return random.choices(ks, weights=ws, k=1)[0]


def shape_hint(cfg):
    """拼成一段给提示词用的话：这一轮说几条、每句多长。"""
    if not cfg:
        return ""
    rows = cfg.get("rows", "mid")
    ln = cfg.get("len", "mid")

    line = _LEN_LINE.get(ln, "")
    if rows == "few" and ln == "long":
        line = _ESSAY_LINE + " " + line
    return line


def temp_of(cfg):
    return (cfg or {}).get("temp", DEFAULTS["temp"])


def penalties_of(cfg):
    """返回 (frequency_penalty, presence_penalty)，0 表示不传。"""
    c = cfg or {}
    return (c.get("freq", 0.0) or 0.0, c.get("pres", 0.0) or 0.0)


def enhance_on(cfg):
    """总开关。关着 = 强化拟人整层失效，回到 11-13 之前。"""
    try:
        return bool((cfg or {}).get("enhance", False))
    except Exception:
        return False


def samples_on(cfg):
    """说话样本开没开。总开关关着就一律关。"""
    if cfg is None:
        from config import SPEECH_SAMPLES_ENABLED
        return SPEECH_SAMPLES_ENABLED
    if not enhance_on(cfg):
        return False
    return bool(cfg.get("sample", True))


def plain_on(cfg):
    """说人话开没开。总开关关着就一律关。"""
    if cfg is None:
        from config import QUENCH_ENABLED
        return QUENCH_ENABLED
    if not enhance_on(cfg):
        return False
    return bool(cfg.get("plain", True))


def tier_of(temp):
    """温度翻成一个人能懂的词。"""
    t = temp or 0
    if t <= 0.65:
        return "很稳"
    if t <= 0.85:
        return "正常"
    if t <= 1.0:
        return "活泼"
    return "飘"

def knows_us_on(cfg):
    """要不要让她记得在一起多少天。默认开。

    关了之后：她问他"认识几天"不会直接报数字，也不会被禁止说"刚认识"——
    等于退回 2026-11-13 之前那套。
    """
    try:
        return bool((cfg or {}).get("knows_us", True))
    except Exception:
        return True


def _gated(cfg, key):
    """总开关关着时，所有子开关一律视为关。"""
    if not enhance_on(cfg):
        return False
    return bool((cfg or {}).get(key, False))
