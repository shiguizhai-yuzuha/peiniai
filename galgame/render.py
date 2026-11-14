# -*- coding: utf-8 -*-
"""JSON → Ren'Py 代码。

设计原则：
1. 白名单：不认识的字段一律忽略，不报错
2. 容错：缺字段给默认值，坏数据跳过
3. 转义：`{` `[` `"` 必须处理，否则 lint 直接报错
4. 纯函数：不读文件、不联网，方便测
"""

# 角色名 → Ren'Py 变量名
CHAR_MAP = {
    "柚叶": "youye",
    "浮波柚叶": "youye",
    "流萤": "liuying",
}
DEFAULT_CHAR = "youye"

# 这一次渲染里所有合法的 label（render_all 会填）
_ALLOWED_LABELS = set()

# 模板里定义的背景（不在这个集合里的一律用 black）
VALID_BG = {"black", "bg_station", "bg_street", "bg_lake", "bg_room", "bg_night"}


def esc(s) -> str:
    """把文本变成能安全放进 Ren'Py 双引号里的字符串。

    Ren'Py 里：
      反斜杠是转义符 → 必须写成两个 ← 最先处理，否则会吃掉后面的引号
      { 是文字标签 → 要写成 {{
      [ 是变量插值 → 要写成 [[
      " 会截断字符串 → 要写成 \\"
      换行不能直接出现
    """
    if s is None:
        return ""
    text = str(s)
    text = text.replace("\r", " ").replace("\n", " ")
    # 顺序很重要：先转义反斜杠，再转义引号（否则新加的反斜杠会被二次转义）
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "{{").replace("[", "[[")
    text = text.replace('"', '\\"')
    # 去掉控制字符
    text = "".join(ch for ch in text if ch >= " " or ch == "\t")
    return text.strip()


def char_var(who: str) -> str:
    """角色名 → 变量名。不认识的用默认角色，绝不报错。"""
    name = (who or "").strip()
    return CHAR_MAP.get(name, DEFAULT_CHAR)


def safe_bg(bg: str) -> str:
    name = (bg or "").strip()
    return name if name in VALID_BG else "black"


def _render_lines(lines, out, indent="    ", start_bg=None):
    """写台词。背景变了才重新 scene —— 否则同一个背景会被写十几次。"""
    current = safe_bg(start_bg) if start_bg else None
    for ln in lines or []:
        if not isinstance(ln, dict):
            continue

        bg = ln.get("bg")
        if bg:
            want = safe_bg(bg)
            if want != current:
                out.append(f"{indent}scene {want} with fade")
                out.append("")
                current = want

        text = esc(ln.get("text"))
        if not text:
            continue

        who = (ln.get("who") or "").strip()
        if who:
            out.append(f'{indent}{char_var(who)} "{text}"')
        else:
            out.append(f'{indent}"{text}"')
        out.append("")


def _render_choices(choices, out, indent="    "):
    valid = [c for c in (choices or []) if isinstance(c, dict) and esc(c.get("text"))]
    if not valid:
        return

    out.append(f"{indent}menu:")
    for ch in valid:
        text = esc(ch.get("text"))
        out.append(f'{indent}    "{text}":')

        body = []
        aff = ch.get("affection", 0) or 0
        tru = ch.get("trust", 0) or 0
        if aff:
            body.append(f"{indent}        $ add_affection({int(aff)})")
        if tru:
            body.append(f"{indent}        $ add_trust({int(tru)})")
        reply = esc(ch.get("reply"))
        if reply:
            body.append(f'{indent}        "{reply}"')

        # Ren'Py 的空 block 会报错，必须有语句
        if not body:
            body.append(f"{indent}        pass")

        out.extend(body)
        out.append("")
    out.append("")


def render_day(day: dict, *, is_last: bool = False) -> str:
    """把一天的 JSON 渲染成一个 .rpy 文件的完整内容。"""
    d = day.get("day")
    try:
        d = int(d)
    except (TypeError, ValueError):
        d = 1

    title = esc(day.get("title"))
    role = esc(day.get("role"))

    out = []
    head = f"# Day {d}"
    if role:
        head += f" · {role}"
    if title:
        head += f" · {title}"
    out.append(head)
    out.append(f"label day{d}:")
    out.append("")

    _render_lines(day.get("lines"), out)
    _render_choices(day.get("choices"), out)

    end_text = esc(day.get("end"))
    if end_text:
        out.append(f'    "{end_text}"')
        out.append("")

    out.append("    jump ending" if is_last else f"    jump day{d + 1}")
    out.append("")

    return "\n".join(out)


def render_script(days: list) -> str:
    """生成 script.rpy（入口 + 结局）。"""
    out = [
        "# script.rpy —— 自动生成",
        "",
        "label start:",
        "    jump day1",
        "",
        "label ending:",
        '    "（完）"',
        "    return",
        "",
    ]
    return "\n".join(out)


def render_all(data: dict) -> dict:
    """整个 JSON → {文件名: 内容}。

    支持两种格式：
      旧：day 下面直接有 lines / choices / end
      新：day 下面是 scenes 数组（每一幕有 id、自己跳转）
    """
    global _ALLOWED_LABELS

    days = data.get("days") or []
    files = {}

    # 先把所有 label 收一遍，后面跳转要校验
    labels = {"start", "ending"}
    for i, day in enumerate(days):
        if not isinstance(day, dict):
            continue
        try:
            d = int(day.get("day"))
        except (TypeError, ValueError):
            d = i + 1
        labels.add("day%d" % d)
        for j, sc in enumerate(day.get("scenes") or [], 1):
            if isinstance(sc, dict):
                labels.add(_scene_id(sc, d, j))
    _ALLOWED_LABELS = labels

    for i, day in enumerate(days):
        if not isinstance(day, dict):
            continue
        d = day.get("day")
        try:
            d = int(d)
        except (TypeError, ValueError):
            d = i + 1
        is_last = (i == len(days) - 1)
        if has_scenes(day):
            files[f"day{d}.rpy"] = render_day_scenes(day, is_last=is_last)
        else:
            files[f"day{d}.rpy"] = render_day(day, is_last=is_last)

    files["script.rpy"] = render_script(days)
    return files

# ============ 多幕 + 分支 ============

def _scene_id(scene, day_no, idx):
    """场景 id。优先用 JSON 里的，没有就用 d{天}s{幕}。"""
    sid = (scene.get("id") or "").strip()
    if sid:
        return sid
    return "d%ds%d" % (day_no, idx)


def _render_scene(scene, sid, day_no, idx, total, is_last_day, out):
    """渲染一幕：label + 内容 + 跳转。"""
    out.append("label %s:" % sid)
    out.append("")

    bg = safe_bg(scene.get("bg"))
    out.append("    scene %s with fade" % bg)
    out.append("")

    _render_lines(scene.get("lines"), out, start_bg=bg)

    choices = [c for c in (scene.get("choices") or [])
               if isinstance(c, dict) and esc(c.get("text"))]

    if choices:
        # 下一站：每个选项的 next，没有就用"下一幕 / 下一天"
        default_next = ("d%ds%d" % (day_no, idx + 1)) if idx < total else None

        out.append("    menu:")
        for ch in choices:
            out.append('        "%s":' % esc(ch.get("text")))
            body = []
            aff = ch.get("affection", 0) or 0
            tru = ch.get("trust", 0) or 0
            if aff:
                body.append("            $ add_affection(%d)" % int(aff))
            if tru:
                body.append("            $ add_trust(%d)" % int(tru))
            reply = esc(ch.get("reply"))
            if reply:
                body.append('            "%s"' % reply)

            nxt = (ch.get("next") or "").strip()
            if nxt and nxt in _ALLOWED_LABELS:
                body.append("            jump %s" % nxt)
            elif default_next:
                body.append("            jump %s" % default_next)
            else:
                body.append("            jump ending" if is_last_day else
                            "            jump day%d" % (day_no + 1))

            if not body:
                body = ["            pass"]
            out.extend(body)
            out.append("")
        out.append("")

    # 有 menu 时 end 走不到（每个选项都跳走了），所以不写
    end_text = esc(scene.get("end"))
    if end_text and not choices:
        out.append('    "%s"' % end_text)
        out.append("")

    # 有 menu 时不补 jump —— 每个选项自己跳走了
    if choices:
        pass
    else:
        if idx < total:
            out.append("    jump d%ds%d" % (day_no, idx + 1))
        elif is_last_day:
            out.append("    jump ending")
        else:
            out.append("    jump day%d" % (day_no + 1))
    out.append("")


def render_day_scenes(day: dict, *, is_last: bool = False) -> str:
    """把一个"多幕"的 day 渲染成一整段 .rpy。"""
    d = day.get("day")
    try:
        d = int(d)
    except (TypeError, ValueError):
        d = 1

    scenes = [s for s in (day.get("scenes") or []) if isinstance(s, dict)]

    out = []
    head = "# Day %d" % d
    if day.get("role"):
        head += " · %s" % esc(day.get("role"))
    if day.get("title"):
        head += " · %s" % esc(day.get("title"))
    out.append(head)

    # 当天入口：跳到第一幕
    out.append("label day%d:" % d)
    out.append("    jump %s" % _scene_id(scenes[0], d, 1))
    out.append("")

    total = len(scenes)
    for i, sc in enumerate(scenes, 1):
        _render_scene(sc, _scene_id(sc, d, i), d, i, total, is_last, out)

    return "\n".join(out)


def has_scenes(day: dict) -> bool:
    return bool(day.get("scenes"))


