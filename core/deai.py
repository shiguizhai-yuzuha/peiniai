"""淬 · 去 AI 味

把模型写出来的话，过一遍水。

为什么叫淬
    打铁的最后一道：把烧红的铁按进水里。
    不是把铁变软，是让它硬起来，把杂质逼出来。
    这一步不生产任何内容，只把不该在的东西去掉。

负责
    · 删掉结尾的追问句
    · 删掉总结句、礼貌语
    · 删掉 *动作* （动作） 【字幕】 这类描写
    · 把书面词换成口语词
    · 一条消息最多留两句
    · 和上一轮开头重复的部分，去掉

不负责
    · 不改事实、不改人称
    · 不判断这句话该不该说（那是 core/guard）
    · 不生成任何内容

两条入口
    quench_segment(text)   流式阶段用。只做安全的局部替换，不改结构。
    quench_full(text, prev) 整条消息用。做完上面全部七条。

为什么要分两个
    流式是一段一段吐的，"截到两句"在片段上做就是错的。
    所以结构类规则只在拿到整条消息时用。
"""

import re

# ============================================================
# 规则一：结尾追问
# AI 爱在最后加一句"你觉得呢？""要不要试试？"
# 那是客服语气，不是人。
# ============================================================

_RE_TRAIL_ASK = re.compile(
    r"(你觉得呢|你说呢|是不是|好不好|怎么样|要不要|可以吗|对吗|好吗"
    r"|你说是不是|你说好不好)[？?]\s*$"
)

# 这些是"她主动问"的开头，不算尾巴，要留
_RE_LEAD_ASK = re.compile(r"^\s*(你|他)[^。！？]{0,10}[？?]")


# ============================================================
# 规则二：总结句
# ============================================================

_SUMMARY_WORDS = ("总之", "总的来说", "综上", "所以说", "总结一下",
                  "希望能帮到你", "希望这些对你有帮助", "以上",
                  "整体来说", "归根结底")


# ============================================================
# 规则三：礼貌语
# ============================================================

_POLITE_WORDS = ("谢谢你的分享", "谢谢你愿意", "很高兴你告诉我",
                 "很高兴你愿意", "感谢你的信任", "不好意思，我",
                 "不好意思打扰", "很荣幸", "非常理解")


# ============================================================
# 规则四：动作描写
# *轻轻一笑*  （沉默）  【停顿】  这类是网文腔，不是聊天
# ============================================================

# 2026-11-13：上限从 20/16 提到 40。
# 之前"（正低头给一只瓷兔子描耳朵，笔尖停在半空）"有 21 字，
# 超出了 16 字的限制，整条漏过去——这就是"开着说人话却没区别"的原因。
_RE_ACT_STAR = re.compile(r"\*[^*\n]{1,40}\*")
_RE_ACT_PAREN = re.compile(r"[（(][^）)\n]{1,40}[）)]")
_RE_ACT_BRACK = re.compile(r"【[^】\n]{1,40}】")

# 括号里这些是正常的（不是动作），要留
_KEEP_PAREN = ("（笑）", "（哭）", "（嗯", "（真的", "(笑)", "(哭)")


# ============================================================
# 规则五：书面词替换
# ============================================================

_REPLACE = [
    ("似乎有点", "有点"),
    ("似乎", "像"),
    ("仿佛", "像"),
    ("不禁", ""),
    ("些许", "有点"),
    ("微微", ""),
    ("缓缓", "慢慢"),
    ("默默地", ""),
    ("静静", ""),
    ("或许", "可能"),
    ("也许", "可能"),
    ("然而", "但"),
    ("因此", "所以"),
    ("于是", "然后"),
    ("随即", "就"),
    ("顿时", "一下子"),
    ("瞬间", "一下子"),
    ("凝视", "看"),
    ("注视着", "看着"),
    ("轻声", ""),
    ("温柔地", ""),
    ("认真地说", "说"),
    ("说道", "说"),
    ("问道", "问"),
]


# ============================================================
# 规则六：只留两句
# ============================================================

_RE_SENT_END = re.compile(r"[。！？!?]")
MAX_SENTENCES = 2


# ============================================================
# 规则七：开头去重
# ============================================================

def _first_clause(text):
    """取开头第一小句，用来和上一轮比。"""
    m = re.match(r"^[^，。！？\n]{0,12}", text or "")
    return (m.group(0) if m else "").strip()


# ============================================================
# 三个内部步骤
# ============================================================

def _strip_actions(text):
    """删动作描写。删完是空的就返回空串，交给调用方兜底。"""
    before = text

    def _keep_paren(m):
        s = m.group(0)
        return s if s in _KEEP_PAREN else ""

    text = _RE_ACT_STAR.sub("", text)
    text = _RE_ACT_BRACK.sub("", text)
    text = _RE_ACT_PAREN.sub(_keep_paren, text)

    if text != before:
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text


def _swap_words(text):
    for a, b in _REPLACE:
        if a in text:
            text = text.replace(a, b)
    # 替换后可能出现连续空格或句首标点
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^[，、。]", "", text.strip())
    return text.strip()


def _cut_sentences(text, n=MAX_SENTENCES):
    """超过 n 个句末标点，截到第 n 个。"""
    count = 0
    for m in _RE_SENT_END.finditer(text):
        count += 1
        if count >= n:
            rest = text[m.end():]
            # 后面还有内容才截
            if rest.strip():
                return text[:m.end()].strip()
            return text.strip()
    return text.strip()


def _drop_tail_ask(text):
    """删结尾的追问句（整句）。"""
    if _RE_LEAD_ASK.match(text):
        # 一开口就在问，那是她的主动，不删
        return text
    m = _RE_TRAIL_ASK.search(text)
    if not m:
        return text
    # 从上一个句末标点之后开始算这一句
    head = text[:m.start()]
    cut = max(head.rfind("。"), head.rfind("！"), head.rfind("？"),
              head.rfind("\n"), head.rfind("，"))
    keep = text[:cut + 1].strip() if cut >= 0 else ""
    # 删完啥都不剩，就退回原文（宁可留着问句，也不要空）
    return keep if keep else text


def _drop_lines_with(text, words):
    out = []
    for line in text.split("\n"):
        if any(w in line for w in words):
            continue
        out.append(line)
    res = "\n".join(out).strip()
    return res


# ============================================================
# 对外：流式片段
# ============================================================

def quench_segment(text):
    """流式阶段用。只做安全的局部替换。

    做：删动作描写、换书面词
    不做：截句、删尾问、去重（片段上做会出错）
    """
    if not text:
        return text
    try:
        s = _strip_actions(text)
        if not s:
            # 整段都是动作，改成一句她的话，别让气泡空着
            return "嗯。"
        s = _swap_words(s)
        return s if s else text
    except Exception:
        return text


# ============================================================
# 对外：整条消息
# ============================================================

def quench_full(text, prev_reply=""):
    """整条消息用。七条全过一遍。

    prev_reply 是她上一轮说的话，用来做开头去重。
    """
    if not text:
        return text
    try:
        s = text

        # ④ 动作描写
        s = _strip_actions(s) or "嗯。"

        # ② 总结句、③ 礼貌语：整行删
        s = _drop_lines_with(s, _SUMMARY_WORDS)
        s = _drop_lines_with(s, _POLITE_WORDS)
        if not s.strip():
            s = "嗯。"

        # ⑤ 书面词
        s = _swap_words(s)

        # ① 结尾追问
        s = _drop_tail_ask(s)

        # ⑥ 只留两句
        s = _cut_sentences(s, MAX_SENTENCES)

        # ⑦ 开头去重
        if prev_reply:
            a = _first_clause(s)
            b = _first_clause(prev_reply)
            if a and a == b and len(s) > len(a):
                s = s[len(a):].lstrip("，、 ").strip() or s

        return s.strip() or text
    except Exception:
        return text


# ============================================================
# 自测：python -m core.deai
# ============================================================

if __name__ == "__main__":
    cases = [
        ("*轻轻一笑* 今天累了就早点睡吧。你觉得呢？", ""),
        ("我理解你的感受。总之，你要好好照顾自己。希望能帮到你。", ""),
        ("似乎有点冷。缓缓地，她把窗关上了。", ""),
        ("那就不干了。先睡。明天再说。别想太多。", ""),
        ("谢谢你愿意告诉我。我在这儿陪着你。", ""),
        ("嗯。", ""),
        ("外面下雨了。", ""),
    ]
    print("")
    print("  ── 淬 · 自测 ──")
    print("")
    for raw, prev in cases:
        out = quench_full(raw, prev)
        print("  原：%s" % raw)
        print("  出：%s" % out)
        print("")
