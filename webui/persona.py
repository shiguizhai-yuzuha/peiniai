"""衣冠 · 角色：创建、切换、删除。

负责
  · 创建面板的显隐
  · 自定义角色增删
  · 切换角色（含背景和历史）

不负责
  · 不生成人设文本（那是 core/persona_gen）"""
# 名字　衣冠 —— 优孟衣冠——穿上谁的衣服，就是谁。


from urllib.parse import quote
import uuid

import gradio as gr

from config import DEFAULT_PERSONA
from core import persona_create
from core import personas
from core import stage
from db import repository as repo
from services import keepsake as gkeep

from webui.state import _input_buffers, _input_lock

from webui.chat import load_history, opening_history
from webui.render import get_bg_style


def toggle_create():
    return gr.update(visible=True)


def _create_fail(msg, session_id):
    """统一的失败返回。"""
    return msg, gr.update(), gr.update(), [], "", session_id


def do_create_persona(name, call_me, quote, state, target, user_id, session_id, raw=""):
    """生成一个私有角色，并把界面切到它。

    具体五步在 core.persona_create 里，这里只管调度和界面。
    """
    err = persona_create.check(name, quote, user_id)
    if err:
        return _create_fail(err, session_id)

    imported = persona_create.import_chat(user_id, raw, call_me)

    r, err = persona_create.generate(user_id, name, call_me, quote,
                                     state, target, imported)
    if err:
        return _create_fail(err, session_id)

    cid, knows, stage, err = persona_create.save(user_id, name, call_me,
                                                 target, r, imported)
    if err:
        return _create_fail(err, session_id)

    key = personas.custom_key(cid)
    choices = personas.list_for_user(user_id)
    history = opening_history(key)
    bg = get_bg_style(key, user_id=user_id)
    new_session = str(uuid.uuid4())

    print(f"[新建角色] user={user_id[:8]} id={cid} name={name} target={target} "
          f"knows={knows} stage={stage}", flush=True)

    msg = (f"✅ **{name}** 已经建好了。\n\n"
           f"她说的第一句是：「{r['opening']}」\n\n"
           f"_她不是你认识的那个人，是根据你给的材料重建的。_")
    return (msg, gr.update(visible=False),
            gr.update(choices=choices, value=key),
            history, bg, new_session)


def do_delete_persona(user_id):
    """删掉这个用户所有的自定义角色，连同对话和记忆。"""
    if not user_id:
        return "⚠️ 请先登录。", gr.update(), gr.update()
    rows = repo.list_custom_personas(user_id)
    if not rows:
        return "（你现在没有自定义角色）", gr.update(), gr.update()
    for r in rows:
        repo.delete_custom_persona(r["id"], user_id)
        print("[删角色] user=%s id=%s name=%s" % (str(user_id)[:8], r["id"], r["name"]),
              flush=True)
    choices = personas.list_for_user(user_id)
    return ("✅ 已经删掉了。连对话和记忆一起清的。",
            gr.update(choices=choices, value=DEFAULT_PERSONA),
            gr.update(visible=True))


def _my_personas(user_id):
    try:
        return [x["persona"] for x in gkeep.list_personas(user_id)]
    except Exception:
        return []


def switch_persona(persona, user_id, session_id):
    print(f"[切换] persona={persona} user={user_id[:8] if user_id else 'None'}", flush=True)

    if user_id:
        with _input_lock:
            _input_buffers.pop(user_id, None)

    history = load_history(user_id, persona) if user_id else []
    new_bg = get_bg_style(persona, user_id=user_id)
    new_session = str(uuid.uuid4())

    return history, new_bg, new_session
