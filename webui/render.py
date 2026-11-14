"""设色 · HTML 渲染：把数据变成页面片段。

负责
  · 读 templates/ 下的模板
  · 背景样式、静态 CSS 拼接
  · 里程碑卡、关系条、她的主页

不负责
  · 不写数据库
  · 不处理点击事件"""
# 名字　设色 —— 国画术语：在墨线上上颜色。数据是线，它是色。


import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from config import LOGIN_BACKGROUND
from config import PERSONAS
from core import milestones
from core import permissions
from core import personas
from core import relationship
from core import ring
from core import stage
from db import repository as repo

from webui.helpers import _bg_url, _days_since, _fmt_day


# ============ 模板加载 ============
# HTML 放在 templates/ 目录，改文案不用碰 Python。
_TEMPLATE_DIR = os.path.join(_ROOT, "templates")


def _load_template(name):
    """读一个模板文件。读不到返回空串，不让页面挂掉。"""
    path = os.path.join(_TEMPLATE_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print("[模板] 读不到 %s：%s" % (name, e), flush=True)
        return ""


def get_bg_style(persona=None, is_login=False, user_id=None):
    img_path = None

    if is_login and os.path.exists(LOGIN_BACKGROUND):
        img_path = LOGIN_BACKGROUND

    # 用户自己换过的背景，优先
    if not img_path and user_id and persona:
        try:
            ub = repo.get_user_bg(user_id, persona)
            if ub and ub.get("file") and os.path.exists(ub["file"]):
                img_path = ub["file"]
        except Exception:
            pass

    if not img_path and persona:
        candidate = personas.get_background(persona)
        if candidate and os.path.exists(candidate):
            img_path = candidate

    if not img_path and os.path.exists("static/bg.jpg"):
        img_path = "static/bg.jpg"

    if not img_path:
        return ""

    # 竖版图：同目录下同名加 _v 后缀（没有就沿用横版）
    root, ext = os.path.splitext(img_path)
    v_path = root + "_v" + ext
    if not os.path.exists(v_path):
        v_path = None

    css = f"""
    <style>
    .gradio-container, gradio-app, body {{
        background-image: url('{_bg_url(img_path)}') !important;
        background-size: cover !important;
        background-position: center !important;
        background-attachment: fixed !important;
    }}"""

    # 手机竖屏时换竖版（浏览器自己判断，不需要检测设备）
    if v_path:
        css += f"""
    @media (orientation: portrait) and (max-width: 900px) {{
        .gradio-container, gradio-app, body {{
            background-image: url('{_bg_url(v_path)}') !important;
        }}
    }}"""

    css += """
    </style>
    """
    return css


def get_static_css():
    """样式分两层：
           static/style.css        主样式（旧）
           static/ui/NN_*.css      模块化样式，按文件名顺序拼接
       改样式不用碰 Python。
    """
    base = _ROOT
    out = []

    path = os.path.join(base, "static", "style.css")
    try:
        with open(path, encoding="utf-8") as f:
            out.append(f.read())
    except Exception as e:
        print("[样式] 读不到 style.css：%s" % e, flush=True)

    ui_dir = os.path.join(base, "static", "ui")
    try:
        import glob as _glob
        for p in sorted(_glob.glob(os.path.join(ui_dir, "*.css"))):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append("\n/* ==== %s ==== */\n" % os.path.basename(p))
                    out.append(f.read())
            except Exception as e:
                print("[样式] 读不到 %s：%s" % (p, e), flush=True)
    except Exception as e:
        print("[样式] ui 目录读取失败：%s" % e, flush=True)

    return "\n".join(out)


def render_milestones(user_id, persona):
    """纪念页：只显示已经发生过的事，顶部一条细进度。

    刻意不做的事：不显示"未解锁 ???"的占位卡——还没发生的事不该剧透。
    """
    if not user_id:
        return ("<div style='padding:40px;text-align:center;color:#bbb;font-size:15px'>"
                "请先登录。</div>")

    # hidden: 开头的是内部标记（彩蛋等），不当成纪念显示
    items = [m for m in repo.get_milestones(user_id, persona)
             if not str(m.get("key", "")).startswith("hidden:")]
    if not items:
        return ("<div style='padding:40px;text-align:center;color:#bbb;font-size:15px'>"
                "还没有什么。<br>你们才刚认识。</div>")

    total = len(milestones.DEFS)
    got = len(items)
    pct = int(got * 100 / total) if total else 0

    bar = (
        "<div style='display:flex;align-items:center;gap:12px;margin:0 0 18px'>"
        "<div style='flex:1;height:6px;background:rgba(255,255,255,0.14);"
        "border-radius:3px;overflow:hidden'>"
        f"<div style='width:{pct}%;height:100%;background:#95ec69'></div>"
        "</div>"
        f"<div style='font-size:12px;color:#9aa0a6;white-space:nowrap'>{got} / {total}</div>"
        "</div>"
    )

    cards = []
    for m in items:
        # 好感跨坎没法还原真实日期（库里没有历史曲线），标成"时间不详"而不是假的日期
        if m.get("key") in ("intimacy_50", "intimacy_80"):
            day = "时间不详"
        else:
            day = _fmt_day(m.get("unlocked_at"))
        title = m.get("title") or ""
        cards.append(
            "<div style='background:rgba(20,20,24,0.74);border-radius:14px;"
            "padding:16px 18px;margin:0 0 12px;border-left:3px solid #95ec69;'>"
            f"<div style='font-size:15px;color:#f2f2f2;line-height:1.6'>{title}</div>"
            f"<div style='font-size:12px;color:#8d8d8d;margin-top:6px'>{day}</div>"
            "</div>"
        )

    return (
        "<div style='max-width:640px;margin:0 auto;padding:8px 0'>"
        f"<div style='color:#bbb;font-size:13px;margin-bottom:10px'>"
        f"和「{persona}」之间，已经发生过的 {got} 件事：</div>"
        + bar
        + "".join(cards)
        + "</div>"
    )


def render_relationship(user_id, persona):
    if not user_id:
        return ""

    # 好感度与表白状态按角色独立：读 user_characters（chat.py 现在写的就是这张表）
    char = repo.get_character_state(user_id, persona)
    intimacy = char.get("intimacy", 0)
    is_lover = bool(char.get("confessed_at"))

    if is_lover:
        stage_label = "恋人"
        heart_str = "💕"
    else:
        display = min(intimacy, 55)
        if intimacy >= 55:
            stage_label = "暧昧期"
            heart_str = "💗"
        else:
            stage = relationship.get_stage(display, False)
            stage_label = relationship.STAGE_NAMES.get(stage, stage)
            hearts = min(5, int(display / 12))
            heart_str = "❤️" * hearts + "🤍" * (5 - hearts)

    # 四向状态环（关系 / 记忆 / 情绪 / 时间）
    try:
        ring_html = ring.render(user_id, persona)
    except Exception as e:
        print("[环] 渲染失败：%s" % e, flush=True)
        ring_html = ""

    return ring_html + (
        f"<div style='font-size:15px;color:rgba(246,241,234,.72);"
        f"letter-spacing:.08em;margin-top:6px'>"
        f"关系：<b style='color:#ffd9b8'>{stage_label}</b> {heart_str}"
        f"</div>"
    )


def render_profile(user_id):
    """个人主页：身份、额度、四个角色的关系、统计。

    数据全是现成的，这里只做展示，不改任何业务逻辑。
    """
    if not user_id:
        return ""

    user = repo.get_or_create_user(user_id) or {}
    role_txt = permissions.role_name(user)

    balance = float(user.get("balance") or 0)
    days = _days_since(user.get("created_at")) + 1
    total_msgs = repo.count_messages(user_id)
    total_ms = len(repo.get_milestones(user_id))

    def stat(caption, value, sub=""):
        sub_html = f'<div style="font-size:11px;color:#a0a5ad">{sub}</div>' if sub else ""
        return (
            '<div style="flex:1;min-width:140px;background:#fff;border:1px solid #e6e8ec;'
            'border-radius:12px;padding:14px 16px">'
            f'<div style="font-size:12px;color:#8b9099">{caption}</div>'
            f'<div style="font-size:18px;font-weight:600;color:#20242b;margin-top:2px">{value}</div>'
            f'{sub_html}</div>'
        )

    mem_n = repo.count_memories(user_id)
    head = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px">'
        + stat("身份", role_txt)
        + stat("剩余额度", f"{balance:.2f} 元", "1 元 ≈ 100 条")
        + stat("来过", f"{days} 天")
        + stat("说话", f"{total_msgs} 句", f"所有角色合计 · 纪念 {total_ms} 件")
        + stat("她记得", f"{mem_n} 件", "在下面「她的记忆」里")
        + "</div>"
    )

    # 按好感排序：把真的在聊的角色放前面。
    # 2026-11-13：他看见第一张是 0 好感的角色，配着"说话 9591 句"，
    # 就以为整段关系被抹了。顺序改一下，误会就没有了。
    _order = list(PERSONAS)          # PERSONAS 可能是 dict，不能 .index()
    _rows = []
    for _i, p in enumerate(_order):
        _st = repo.get_character_state(user_id, p) or {}
        _rows.append((float(_st.get("intimacy") or 0), _i, p))
    _rows.sort(key=lambda x: (-x[0], x[1]))

    cards = []
    for _ in _rows:
        p = _[2]
        st = repo.get_character_state(user_id, p) or {}
        intimacy = float(st.get("intimacy") or 0)
        is_lover = bool(st.get("confessed_at"))
        stage = relationship.get_stage(intimacy, is_lover)
        together = (_days_since(st.get("confessed_at")) + 1) if is_lover else 0
        line = relationship.stage_line(stage, intimacy, is_lover, together)
        pct = relationship.calc_progress(intimacy, stage)

        cards.append(
            '<div style="background:#fff;border:1px solid #e6e8ec;border-radius:14px;'
            'padding:16px 18px">'
            '<div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<div style="font-size:15px;font-weight:600;color:#20242b">{p}</div>'
            f'<div style="font-size:12px;color:#a0a5ad">{intimacy:.0f}</div>'
            "</div>"
            '<div style="height:6px;background:#eef0f3;border-radius:99px;overflow:hidden;'
            'margin:10px 0">'
            f'<i style="display:block;height:100%;width:{pct}%;'
            'background:linear-gradient(90deg,#7ba7a0,#c8553d)"></i>'
            "</div>"
            f'<div style="font-size:12px;color:#6b7280;line-height:1.7">{line}</div>'
            "</div>"
        )

    return (
        '<div style="max-width:780px">'
        + head
        + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px">'
        + "".join(cards)
        + "</div></div>"
    )
