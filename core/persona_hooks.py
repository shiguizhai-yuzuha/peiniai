# -*- coding: utf-8 -*-
"""角色专属机制

有些角色身上带着一条"只有她才有的线"：
- 薇薇安：确信度（她不确定你是不是真的喜欢她）

（叶瞬光的遗忘机制已在 2026-10-29 拆除：它让用户为了她"忘掉"而难过，
  成本大于收益。叶瞬光现在和别的角色一样，正常记忆。）

以后加角色，只在这张表里加一行，不要在别处写 if。

约定：
- 所有函数都不抛异常，出问题就当没这个机制。
"""

# 角色 → 机制
PERSONA_HOOKS = {
    "薇薇安": {"certainty": True},
}

# 记忆类型（key 的前缀）。现在没有遗忘机制了，这张表留着当分类用。
KEEP_PREFIXES = ("fact", "user", "name", "relation", "promise",
                 "moment", "event")


def hooks_of(persona):
    """取一个角色的机制配置。没有就返回空字典。"""
    try:
        return PERSONA_HOOKS.get(persona) or {}
    except Exception:
        return {}


def has(persona, name):
    return bool(hooks_of(persona).get(name))


