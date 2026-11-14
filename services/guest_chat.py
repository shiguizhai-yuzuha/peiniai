# -*- coding: utf-8 -*-
"""游客版的回复路径。

不走 memory.build_messages，不走数据库，不走语气引擎。
只做四件事：

    persona 提示词
    + 十轮的剧本提示（services/guest.py 的 arc_prompt）
    + 游客这几轮的历史
    + 这一句

为什么简化：游客本来就没有记忆，检索用不上；
而且不动老代码，出问题伤不到真实用户。
"""

import random

from config import (
    PERSONAS, DEFAULT_PERSONA, OUTPUT_FORMAT_PROMPT, MODEL,
    TEMPERATURE, MAX_TOKENS,
)
from core.client import client

from services import guest

# 游客轮的条数：不超过 3 条，免得一开始就话痨
_MSG_RULE = """## 这一次说几条

这一次回 1 到 3 条，用 <msg> 分开。条数自己定，不要固定。
句子短。像发微信。"""


def _persona_prompt(persona):
    return PERSONAS.get(persona) or PERSONAS[DEFAULT_PERSONA]


def _history(token):
    """游客的历史，转成 API 用的 messages。"""
    s = guest.get(token)
    if not s:
        return []
    return [{"role": h["role"], "content": h["content"]} for h in s["history"]]


def build_messages(token, persona, message):
    """拼一次请求。第几轮决定注入哪段剧本提示。

    顺序很重要：阶段提示放在历史**之后**、用户这句**之前**。
    放在前面会被历史冲淡——实测第 2 轮该问的问题没问出来。
    """
    turn = guest.turns_used(token) + 1

    msgs = [{"role": "system", "content": _persona_prompt(persona)}]
    msgs.append({"role": "system", "content": OUTPUT_FORMAT_PROMPT})
    msgs.append({"role": "system", "content": _MSG_RULE})

    msgs += _history(token)

    arc = guest.arc_prompt(turn)
    if arc:
        msgs.append({"role": "system", "content": arc})

    msgs.append({"role": "user", "content": message})
    return msgs


def ask(token, persona, message):
    """跑一轮。返回 (原始文本, 分段列表)。

    原始文本带 <msg>，存进历史（模型要看自己的格式）；
    分段列表给界面用，一条一个气泡。
    """
    msgs = build_messages(token, persona, message)
    r = client.chat.completions.create(
        model=MODEL,
        messages=msgs,
        temperature=TEMPERATURE,
        max_tokens=min(MAX_TOKENS, 400),
    )
    text = (r.choices[0].message.content or "").strip()

    # 去掉可能的前导 <msg>
    while text.startswith("<msg>"):
        text = text[5:].strip()

    segs = [s.strip() for s in text.split("<msg>") if s.strip()]
    if not segs:
        segs = ["……"]
    return text, segs
