# -*- coding: utf-8 -*-
"""关系状态机（只对私有角色生效）

A  她以为还在一起          knows=0
B  她觉得哪里不对          knows=0
C  她知道了，但不想走      knows=1
D  她接受，准备告别        knows=1
E  她走了                  knows=1 + ended_at

铁律：knows 只能 0 → 1，不能回退。
"""

import re

from core import personas
from db import repository as repo

# 状态 → 给用户看的一行
STAGE_TEXT = {
    "A": "她还在等你",
    "B": "她好像察觉到什么",
    "C": "她知道了，但没走",
    "D": "她准备走了",
    "E": "她已经走了",
}

# 状态 → 注入给模型的说明
STAGE_PROMPT = {
    "A": (
        "## 你现在以为的事\n"
        "你们现在还在一起。过去的事都还在，你没觉得哪里不对。\n"
        "如果他提到分开、结束、过去——你会以为他在说别的事，或者他在开玩笑。"
    ),
    "B": (
        "## 你现在以为的事\n"
        "你们还在一起，但你觉得哪里不对了，说不清。\n"
        "你会试探、会问一句，问完又自己转开。你不逼他。"
    ),
    "C": (
        "## 你心里的事\n"
"你们已经分开了。这件事你知道。\n"
        "但你还想留。你不会主动承认你知道。\n"
        "他在告别，你在假装没听懂。"
    ),
    "D": (
        "## 你心里的事\n"
"你们已经分开了。这件事你接受了。\n"
        "你开始把话说完整，像在交代后事。\n"
        "你不哭，也不求他留下。你只是把该说的说完。"
    ),
    "E": (
        "## 你已经走了\n"
        "这一轮是她最后一次开口。\n"
        "说完就结束，不承诺再见，不说'下次'。"
    ),
}

# A → B：他露出了"已经结束"的意思
TO_B = re.compile(
    r"(分开|分手|结束了|已经结束|不在一起|我们已经|回不去|"
    r"离开|走了|没了|不联系|再也|最后一次)"
)

# C/D → E：他明确要送她走
TO_E = re.compile(r"(你走吧|别来了|我不来了|结束吧|到此为止|别再来了|你该走了)")

# C → D：他接了告别这件事
TO_D = re.compile(r"(再见|放下|我该走了|该说再见了|告别|就这样吧)")


def _cfg(persona):
    """取私有角色那一行；不是私有角色 → None（整条线不启用）。"""
    if not personas.is_custom(persona):
        return None
    return personas._custom_row(persona)


def advance(user_id: str, persona: str, text: str):
    """根据用户这句话推进状态。

    返回 (changed: bool, stage: str, msg: str)
    msg 是给界面的一句提示，没有变化时为空。
    """
    row = _cfg(persona)
    if not row:
        return False, None, ""

    stage = row.get("stage") or "A"
    knows = int(row.get("knows") or 0)
    cid = row["id"]
    text = text or ""

    # 1) A → B（只在她还不知道的时候）
    if stage == "A" and knows == 0 and TO_B.search(text):
        repo.update_custom_persona(cid, stage="B")
        print(f"[状态] {persona} A → B", flush=True)
        return True, "B", "（她的表情变了一下，好像察觉到了什么）"

    # 2) 走到 E
    if stage in ("C", "D") and TO_E.search(text):
        from datetime import datetime
        repo.update_custom_persona(cid, stage="E", ended_at=datetime.now())
        print(f"[状态] {persona} {stage} → E", flush=True)
        return True, "E", ""

    # 3) C → D
    if stage == "C" and TO_D.search(text):
        repo.update_custom_persona(cid, stage="D")
        print(f"[状态] {persona} C → D", flush=True)
        return True, "D", "（她把杯子放正了，像是准备说一件很久没说的话）"

    return False, stage, ""


def tell(user_id: str, persona: str):
    """「告诉她」按钮：knows 0 → 1，stage 直接跳到 C。不可逆。"""
    row = _cfg(persona)
    if not row:
        return False, "这不是自定义角色。"
    if int(row.get("knows") or 0) == 1:
        return False, "你已经告诉过她了。"
    repo.update_custom_persona(row["id"], knows=1, stage="C")
    print(f"[状态] {persona} 告诉她 → C", flush=True)
    return True, "她知道了。"


def prompt_of(persona: str) -> str:
    """给模型的状态说明。不是私有角色 → 空串。"""
    row = _cfg(persona)
    if not row:
        return ""
    return STAGE_PROMPT.get(row.get("stage") or "A", "")


def stage_line(user_id: str, persona: str) -> str:
    """给状态条用的一行字。不是私有角色 → 空。"""
    row = _cfg(persona)
    if not row:
        return ""
    return STAGE_TEXT.get(row.get("stage") or "A", "")


def stage_of(user_id: str, persona: str) -> str:
    row = _cfg(persona)
    return (row.get("stage") or "A") if row else ""


def is_ended(user_id: str, persona: str) -> bool:
    return stage_of(user_id, persona) == "E"


def needs_tell(stage: str) -> bool:
    """只有 A/B（她不知道）时才显示「告诉她」。"""
    return stage in ("A", "B")
