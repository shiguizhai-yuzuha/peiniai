"""看图：先提取事实，再交给人格说话。

为什么要两步：
    直接让她看图，模型只会"扫一眼→给个安全评价"（挺丰盛、挺好看）。
    先按类型把细节抠出来，再让她挑着说，才像真的在看。

规则（写死）：
    只写画面里看得见的
    拿不准的字（牌子、菜单、路牌）宁可说"看不清"
    人数、关系、时间这类不能从图里确定的，只能作推测，不下断言
"""

from __future__ import annotations

import base64
import mimetypes
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 每种图看什么
CHECKLISTS = {
    "食物": "菜品和数量、餐具几副、桌面材质、光线冷暖、有没有店招/桌号牌、锅里在煮什么",
    "游戏": "游戏名或界面特征、段位/等级/血量等数字、角色或武器、小地图、时间",
    "聊天截图": "谁在说话、几句、语气、有没有表情包、界面是哪款 App",
    "人像": "构图、光线、穿着、表情、背景环境（不评论外貌）",
    "文档": "是什么文件、标题、表格还是正文、有没有红笔/标注",
    "风景": "地点特征、天气、时间感、远近层次",
    "其他": "主体是什么、有几个、在哪、光线、能读出的文字",
}

PROMPT = """你是视觉提取器。只做一件事：把图里**看得见**的东西列出来。

先判断图属于哪一类：食物 / 游戏 / 聊天截图 / 人像 / 文档 / 风景 / 其他。
然后按下面要求提取：

{checklist}

输出格式（严格）：
类型：<上面七类之一>
看得见：
- <一条一个细节，最多 7 条，写具体：数量、颜色、位置、文字>
看不清：
- <拿不准的字或物体，没有就写"无">
推测：
- <最多 2 条，必须标注"可能"，不下断言>

硬规则：
1. 只写画面里有的；没看到的不许编
2. 牌子、菜单、屏幕上的字，读不准就放进"看不清"
3. 人数、关系、时间、心情，一律只能进"推测"
4. 不要评价，不要抒情，不要用"很丰盛""挺好看"这种词
"""


def _path_of(url: str) -> str:
    # 已经是存在的绝对路径，直接用
    if os.path.isabs(url) and os.path.isfile(url):
        return url
    if url.startswith("/uploads/"):
        return os.path.join(ROOT, "static", url.lstrip("/"))
    if url.startswith("/"):
        return os.path.join(ROOT, url.lstrip("/"))
    return url


def describe(paths, model: str = "deepseek-flash", timeout_hint: int = 0) -> str:
    """返回一段结构化描述（给下一轮 prompt 用）。失败返回空串。"""
    from core import client

    blocks = [{"type": "text", "text": PROMPT.format(checklist=CHECKLISTS["其他"])}]
    used = 0
    for p in (paths or [])[:3]:
        full = _path_of(p)
        if not os.path.isfile(full):
            continue
        mime = mimetypes.guess_type(full)[0] or "image/jpeg"
        with open(full, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        blocks.append({"type": "image_url",
                       "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}})
        used += 1
    if not used:
        return ""

    buf = []
    try:
        for delta, _u in client.stream_chat(
                [{"role": "user", "content": blocks}],
                temperature=0.2, max_tokens=500, model=model,
                extra_body={"thinking": {"type": "disabled"}}):
            if delta:
                buf.append(delta)
    except Exception as e:
        print("[看图] 提取失败：%s" % e, flush=True)
        return ""
    return "".join(buf).strip()
