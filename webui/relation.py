"""红线 · 关系：告白与阶段推进。

负责
  · 「告诉她」的确认与执行
  · 关系阶段刷新
  · 里程碑页打开

不负责
  · 不改数据库里的四维（那是 core/relationship）"""
# 名字　红线 —— 月老手里那根线。关系到了，才牵得上。


import gradio as gr

from core import personas
from core import stage
from db import repository as repo

from webui.render import render_milestones


def open_milestones(user_id, persona):
    """打开纪念页：藏起聊天区，渲染卡片。"""
    return (
        gr.update(visible=False),                          # chat_group
        gr.update(visible=True),                           # milestone_group
        render_milestones(user_id, persona),               # milestone_html
    )


def show_tell_confirm():
    return gr.update(visible=True)


def hide_tell_confirm():
    return gr.update(visible=False)


def refresh_stage(user_id, persona):
    """刷新状态条 / 告诉她按钮 / 告别页。非私有角色 → 全空。"""
    empty = ("", gr.update(visible=False), "", gr.update(visible=False))
    if not user_id or not persona or not personas.is_custom(persona):
        return empty

    st = stage.stage_of(user_id, persona)
    line = stage.stage_line(user_id, persona)
    bar = ("**%s**" % line) if line else ""

    if st != "E":
        hint = ""
        if stage.needs_tell(st):
            hint = ("\n\n_她还不知道你们已经结束了。如果你告诉她，就回不去了。_")
        return (bar + hint, gr.update(visible=stage.needs_tell(st)),
                "", gr.update(visible=False))

    rows = repo.get_all_messages(user_id, persona)
    body = []
    for m in rows:
        who = "她" if m["role"] == "assistant" else "我"
        txt = (m["content"] or "").replace("<msg>", "  ")
        body.append("%s｜%s" % (who, txt))
    text = "\n".join(body)

    md = ("## 她走了\n\n"
          "她说过的话，都在下面。\n\n"
          "_这些是真的。发生过。_\n\n---\n\n" + text)
    return bar, gr.update(visible=False), md, gr.update(visible=True)


def do_tell(user_id, persona):
    """「告诉她」按钮。不可逆。"""
    if not user_id or not persona:
        return "⚠️ 请先登录。", gr.update(visible=False), "", gr.update(visible=False)
    ok, msg = stage.tell(user_id, persona)
    print("[告诉她] user=%s persona=%s ok=%s" % (str(user_id)[:8], persona, ok), flush=True)
    bar, tell_vis, fmd, fvis = refresh_stage(user_id, persona)
    return msg, tell_vis, fmd, fvis


def _refresh_stage_wrap(u, p):
    return refresh_stage(u, p)
