# -*- coding: utf-8 -*-
"""聊天记录导入：把一段对话文本，提炼成"她的语气"和"你们的经历"

支持粘贴任意格式的文本，尽量从中认出"谁说了什么"。
不追求格式完美，追求"能用"。
"""

import json
import re

from core.client import client
from config import MODEL

# 常见导出格式的前缀
SPEAKER_PATTERNS = [
    re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?([^\s:：]{1,12})[:：]\s*(.+)$"),
    re.compile(r"^\s*([^\s:：]{1,12})\s{2,}(.+)$"),
]

EXTRACT_PROMPT = """你会收到一段两个人的聊天记录。

你的任务：从中提炼出"其中一个人"的说话方式和共同经历。

## 规则

1. **只提炼文本里真实出现的东西。** 没有的，一个字都不许编。
2. shared 至少写 3 条。写她关心什么、他说过什么、他们常聊什么，
   不要返回空数组。只有文本完全没有内容时才允许空，并把 confidence 标 low。
2. 如果分不清哪句是谁说的，就按"更短、更口语的一方"来推测，
   并在结果里标注"推测"。
3. 不要复述隐私细节（地址、学校、电话）。遇到这类，跳过。

## 输出格式

只输出 JSON：

{
  "her_style": "她的说话方式，200 字以内。句子长短、语气词、标点习惯、会不会反问、生气/高兴什么样",
  "her_lines": ["她说的、最有代表性的原话，3-6 句"],
  "shared": ["你们共同的经历，每条 20 字以内，最多 8 条"],
  "time_span": "从什么时候到什么时候（能从文本里看出来就写，看不出来写空）",
  "confidence": "high / medium / low"
}
"""


def _guess_lines(raw, my_name=""):
    """粗分说话人。返回 [(speaker, text), ...]"""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or len(line) > 300:
            continue
        matched = False
        for pat in SPEAKER_PATTERNS:
            m = pat.match(line)
            if m:
                speaker, text = m.group(1).strip(), m.group(2).strip()
                if 1 <= len(speaker) <= 12 and text:
                    out.append((speaker, text))
                    matched = True
                    break
        if not matched and out and len(line) <= 120:
            # 续行，接到上一句
            spk, prev = out[-1]
            out[-1] = (spk, prev + line)
    return out


def extract(raw, my_name=""):
    """从聊天记录里提炼。返回 dict。"""
    pairs = _guess_lines(raw, my_name)

    if not pairs:
        # 分不出说话人，就把整段当材料
        body = raw[:12000]
    else:
        # 统计谁的句子更短更口语 —— 那大概是"她"
        by = {}
        for spk, text in pairs:
            by.setdefault(spk, []).append(text)

        # 假设说话人里不是"我"的那个是她
        speakers = list(by.keys())
        her = None
        if my_name:
            for s in speakers:
                if s != my_name:
                    her = s
                    break
        if her is None and len(speakers) == 2:
            # 取平均句长更短的那个
            her = min(speakers, key=lambda s: sum(len(t) for t in by[s]) / len(by[s]))

        lines = []
        for spk, text in pairs:
            lines.append(f"{spk}: {text}")
        body = "\n".join(lines[:600])

        if her:
            body += f"\n\n（请把「{her}」当作'她'）"

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": body[:14000]},
        ],
        temperature=0.3,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )

    raw_out = resp.choices[0].message.content or "{}"
    m = re.search(r"\{.*\}", raw_out, re.S)
    data = json.loads(m.group(0)) if m else {}

    return {
        "her_style": (data.get("her_style") or "").strip(),
        "her_lines": [str(x).strip() for x in (data.get("her_lines") or []) if str(x).strip()][:6],
        "shared": [str(x).strip() for x in (data.get("shared") or []) if str(x).strip()][:8],
        "time_span": (data.get("time_span") or "").strip(),
        "confidence": data.get("confidence") or "low",
        "turns": len(pairs),
        "tokens": resp.usage.total_tokens if resp.usage else 0,
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
    }
