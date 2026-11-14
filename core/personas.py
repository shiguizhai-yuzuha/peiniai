# -*- coding: utf-8 -*-
"""角色解析层

内置角色来自 config 的字典；私有角色来自数据库（custom_personas 表），
统一用 `custom:<id>` 作为 key。

所有"读角色"的地方都走这里，不再直接查 PERSONAS。
没有私有角色时，行为与以前完全一致。
"""

from config import (
    PERSONAS, OPENINGS, CHARACTER_BACKGROUNDS, DEFAULT_PERSONA,
    SPEECH_SAMPLES_ENABLED,
)


# ==================== 说话的样子（语料） ====================
#
# 这不是规则，是样本。
#
# 模型没有样本，只能按"平均人类"说话——平均人类就是 AI 味。
# 所以给它十二组真的对话，它就有了一个具体的、不平均的人。
#
# 语料从哪来
#   他的句子：开发日志里九份对话归档，只取【你】段落里引号里的原话。
#             【我】是 AI 写的，一个字都没要——用 AI 教 AI 像人，等于拿水洗水。
#   她的句子：手写。要短、不追问、不解释自己。
#
# 挑的标准
#   ① 短。最好十个字以内。
#   ② 不完整。"指着她 手指指" 这种半句话比完整句更像人。
#   ③ 不带书面词。没有似乎、仿佛、因此。
#
# 语料全文在 开发日志/语料_他说话的样子.md（361 条，只用了 12 条）。
# 剩下的没扔——但也没进提示词，因为那里面私事太多，
# 进了提示词就等于每次请求都把私事发一遍。

_SPEECH_SAMPLES = """
【人说话的样子】

下面是真实的对话样本。学的是"怎么说"，不是说什么。

他说：你有空吗
她说：有。

他说：你怎么了
她说：没怎么。

他说：我很难受
她说：那就先躺着。

他说：忍住了没发空间
她说：忍住了挺好。

他说：原来他是这种人
她说：嗯。

他说：外人怎么看我
她说：没人看。

他说：我能不能变好
她说：不知道。

他说：我接受什么了。
她说：你接受了很多。

他说：指着她 手指指
她说：嗯，指谁。

他说：听我骂人可以吗
她说：骂吧。

他说：我该怎么被攻略呢
她说：你自己想办法。

他说：这样不是讨口子吗
她说：是有点。

注意这十二组的共同点：
· 她的话都很短
· 她不追问（不说"你为什么这么想"）
· 她不解释自己（不说"我这样问是因为关心你"）
· 有时候她只回一个字
"""

CUSTOM_PREFIX = "custom:"


# ==================== 判定 ====================

def is_custom(persona) -> bool:
    return isinstance(persona, str) and persona.startswith(CUSTOM_PREFIX)


def custom_id(persona):
    try:
        return int(str(persona).split(":", 1)[1])
    except Exception:
        return None


def custom_key(cid) -> str:
    return f"{CUSTOM_PREFIX}{cid}"


# ==================== 取私有角色 ====================

def _custom_row(persona):
    """取私有角色那一行；不是私有/查不到 → None。"""
    if not is_custom(persona):
        return None
    try:
        from db import repository as repo
        return repo.get_custom_persona(custom_id(persona))
    except Exception:
        return None


# ==================== 四个解析函数 ====================

def get_prompt(persona, user_id=None) -> str:
    """人设提示词。

    内置角色会在末尾接上"说话的样子"那十二组样本。
    私有角色不接——他自己写的人设优先，别被样本冲掉。
    """
    if is_custom(persona):
        row = _custom_row(persona)
        if row and row.get("prompt"):
            return row["prompt"]
        # 私有角色还没生成好人设 → 给一个"正在成形"的占位
        return ("你是一个正在被对方描述的人。"
                "你对他说的每一句关于自己的话都会成为真实的你。"
                "你不知道的，就问他。")

    base = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])

    # 开关优先级：用户设置 > config 总开关
    # 用户在 /voice 里勾掉「说话样本」就真的不接样本了。
    on = SPEECH_SAMPLES_ENABLED
    if user_id:
        try:
            from core import voice_cfg
            on = voice_cfg.samples_on(voice_cfg.load(user_id))
        except Exception:
            pass
    return base + _SPEECH_SAMPLES if on else base


def get_openings(persona, user_id=None):
    """开场白（列表）。"""
    if is_custom(persona):
        row = _custom_row(persona)
        if row and row.get("opening"):
            return [row["opening"]]
        return ["……"]
    lines = OPENINGS.get(persona)
    if lines:
        return lines
    return OPENINGS.get(DEFAULT_PERSONA) or []


def get_background(persona, user_id=None):
    """背景图路径。私有角色默认用通用背景。"""
    if is_custom(persona):
        return None
    return CHARACTER_BACKGROUNDS.get(persona)


def get_catchphrases(persona, user_id=None):
    """口癖（列表）。"""
    if is_custom(persona):
        row = _custom_row(persona)
        if row and row.get("catchphrases"):
            return [x for x in str(row["catchphrases"]).split("|") if x.strip()]
        return []
    from core.memory import CATCHPHRASES
    return CATCHPHRASES.get(persona) or []


def display_name(persona, user_id=None) -> str:
    """给界面看的名字。内置角色直接用 key。"""
    if is_custom(persona):
        row = _custom_row(persona)
        if row and row.get("name"):
            return row["name"]
        return "（未命名）"
    return persona


# ==================== 列表 ====================

def list_builtin():
    return list(PERSONAS.keys())


def list_for_user(user_id):
    """返回 [(显示名, key), ...] —— 内置在前，私有在后。"""
    out = [(p, p) for p in list_builtin()]
    if user_id:
        try:
            from db import repository as repo
            for row in repo.list_custom_personas(user_id):
                key = custom_key(row["id"])
                out.append((row["name"] or "（未命名）", key))
        except Exception:
            pass
    return out


def is_known(persona, user_id=None) -> bool:
    """这个 key 是不是个有效角色。"""
    if is_custom(persona):
        row = _custom_row(persona)
        if not row:
            return False
        if user_id and row.get("user_id") and row["user_id"] != user_id:
            return False
        return True
    return persona in PERSONAS
