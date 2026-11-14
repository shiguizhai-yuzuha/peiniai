# -*- coding: utf-8 -*-
"""确信度：判断"这一句算不算证据"

只有 config.CERTAINTY_CHARACTERS 里的角色才走这条线。
其他角色调用 apply() 会立刻返回 0，不读库、不计算。

规则刻意做得很笨：
  - 可预测：你能一眼看出为什么涨、为什么跌
  - 不会瞎涨：只有明确的话才算
  - 单轮封顶：防止一句话里堆词刷分
"""
from config import CERTAINTY_CHARACTERS
from db import repository as repo

# 顺序很重要：从上往下匹配，命中就停。
# 先匹配"否认"和"承认"，最后才是"提到"。
RULES = (
    (("我不是法厄同", "我不是他", "你认错人了", "我不是那个人"), -50, "否认"),
    (("我就是法厄同", "我是法厄同", "法厄同就是我", "我就是他"), +30, "承认"),
    (("法厄同",), +1, "提到"),
)

MAX_UP_PER_TURN = 30   # 单轮最多涨 30
MAX_DOWN_PER_TURN = 50  # 单轮最多跌 50


def evaluate(text: str):
    """纯函数：给一句话，返回 (delta, reason)。不碰数据库。"""
    if not text:
        return 0, ""
    for words, delta, reason in RULES:
        for w in words:
            if w in text:
                return delta, reason
    return 0, ""


def apply(user_id: str, persona: str, text: str):
    """把这句话的证据记到确信度上。

    返回 (delta, new_value)。不是名单里的角色 → (0, None)，不读库。
    """
    if persona not in CERTAINTY_CHARACTERS:
        return 0, None

    delta, reason = evaluate(text)
    if delta == 0:
        return 0, None

    if delta > MAX_UP_PER_TURN:
        delta = MAX_UP_PER_TURN
    elif delta < -MAX_DOWN_PER_TURN:
        delta = -MAX_DOWN_PER_TURN

    new = repo.change_certainty(user_id, persona, delta)
    print(f"[确信度] user={user_id[:8]} persona={persona} "
          f"{delta:+d}（{reason}）→ {new:.0f}", flush=True)
    return delta, new
