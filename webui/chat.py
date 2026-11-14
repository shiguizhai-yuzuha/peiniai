"""应答 · 聊天：一轮对话的界面侧。

负责
  · 载入历史、开场白
  · respond（旧界面的主回调，流式分段）
  · 游客版对话、清空

不负责
  · 不拼提示词（那是 core/personas + services/chat）
  · 不直接调模型"""
# 名字　应答 —— 它只管开口。不负责记住，也不负责判断该不该说。


import random
import time
import traceback
import uuid

import gradio as gr

from config import INPUT_WAIT_SECONDS
from config import TYPING_HINT_CHANCE
from core import personas
from db import repository as repo
from services import guest
from services import guest_chat
from services.chat import handle_message
from services.chat import split_chunks

from webui.state import _input_buffers, _input_lock

from webui.render import render_relationship


def load_history(user_id, persona):
    if not user_id:
        return []
    history = repo.get_recent_messages(user_id, persona, limit=20)
    result = []
    for m in history:
        if m["role"] == "assistant":
            for chunk in split_chunks(m["content"], max_chunks=20, merge=False):
                result.append({"role": "assistant", "content": chunk})
        else:
            result.append({"role": m["role"], "content": m["content"]})
    return result


def opening_history(persona):
    """聊天记录为空时，让她先说第一句。

    只用于展示，不写进 messages 表——
    这样既不用花 token，也不会污染统计和记忆。
    """
    lines = personas.get_openings(persona)
    if not lines:
        return []
    return [{"role": "assistant", "content": random.choice(lines)}]


def respond(message, chat_history, user_id, session_id, persona, guest_token=None):
    # 游客：只有"没有 user_id 但有凭证"才走免登录。
    # 这样登录之后即使 guest_token 还留着，也不会串到游客路径。
    if guest_token and not user_id:
        yield from _respond_guest(message, chat_history, guest_token, persona)
        return

    if not user_id:
        yield "", chat_history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "⚠️ 请先登录"},
        ], gr.update(), "", gr.update(), gr.update()
        return

    if not message.strip():
        yield "", chat_history, gr.update(), "", gr.update(), gr.update()
        return

    chat_history = chat_history + [{"role": "user", "content": message}]

    # 顶部状态条：像微信标题栏一样显示"XX正在输入……"
    # 它只活在这一轮里，不写进聊天记录，所以刷新不会残留。
    typing = ""
    if random.random() < TYPING_HINT_CHANCE:
        typing = f"{persona}正在输入……"

    yield "", chat_history, gr.update(), typing, gr.update(), gr.update()

    with _input_lock:
        if user_id not in _input_buffers:
            _input_buffers[user_id] = {"messages": [], "seq": 0, "persona": persona}
        _input_buffers[user_id]["messages"].append(message)
        _input_buffers[user_id]["seq"] += 1
        my_seq = _input_buffers[user_id]["seq"]

    time.sleep(INPUT_WAIT_SECONDS)

    with _input_lock:
        buf = _input_buffers.get(user_id)
        if not buf:
            yield "", chat_history, gr.update(), "", gr.update(), gr.update()
            return
        if buf.get("persona") != persona:
            # 2026-11-14 P0：以前这里是「丢弃这一条然后 return」。
            # 但缓冲没被清空，persona 还是旧的，于是之后每一条都被丢——
            # 用户看到的现象就是「切到某个角色后她再也不说话了」。
            # 现在改成：把缓冲换成新角色，并保留刚收到的这一条，继续往下走。
            print(f"[切换] 角色换了，重建缓冲 user={user_id[:8]} -> {persona}", flush=True)
            _input_buffers[user_id] = {"messages": [message], "seq": 1,
                                      "persona": persona}
            buf = _input_buffers[user_id]
            my_seq = 1
        if buf["seq"] != my_seq:
            # 后面还有消息，让最新的那次去处理；状态条清掉，免得卡住
            yield "", chat_history, gr.update(), "", gr.update(), gr.update()
            return
        msgs = buf["messages"].copy()
        _input_buffers[user_id] = {"messages": [], "seq": 0, "persona": persona}

    # 防抖结束：把这一轮收到的几条消息一起交给业务层。
    # 界面上它们已经是独立气泡（上面每收到一条就 yield 过一次聊天记录），
    # 这里传列表，是为了让它们也"一条一行"入库 —— 否则刷新/切角色后会被粘成一条。
    print(f"[缓冲] user={user_id[:8]} persona={persona} 合并 {len(msgs)} 条", flush=True)

    try:
        got_any = False
        for chunk, err in handle_message(user_id, session_id, msgs, persona):
            got_any = True
            content = chunk or err
            typing = ""          # 第一条真回复来了，状态条收掉
            chat_history = chat_history + [{"role": "assistant", "content": content}]
            yield "", chat_history, gr.update(value=render_relationship(user_id, persona)), typing, gr.update(), gr.update()
        if not got_any:
            print(f"[睡眠] 静默处理 user={user_id[:8]}", flush=True)
        yield "", chat_history, gr.update(), "", gr.update(), gr.update()
    except Exception as e:
        print(f"发生异常：{e}")
        traceback.print_exc()
        chat_history = chat_history + [{"role": "assistant", "content": f"⚠️ 出错：{e}"}]
        yield "", chat_history, gr.update(), "", gr.update(), gr.update()


def _respond_guest(message, chat_history, token, persona):
    """游客版的 respond。不写库，只走 guest 内存。

    输出 6 个：msg / chatbot / relationship_html / typing_status
                / guest_save_group / guest_end_md
    """
    KEEP = (gr.update(), gr.update())      # 两个游客组件的默认值

    if not message.strip():
        yield "", chat_history, gr.update(), "", *KEEP
        return

    chat_history = chat_history + [{"role": "user", "content": message}]
    yield "", chat_history, gr.update(), "", *KEEP

    try:
        guest.append(token, "user", message)
        text, segs = guest_chat.ask(token, persona, message)
        guest.append(token, "assistant", text)
        turn = guest.bump_turn(token)

        for s in segs:
            chat_history = chat_history + [{"role": "assistant", "content": s}]
            yield "", chat_history, gr.update(), "", *KEEP

        print("[游客] %s 第 %d 轮，回 %d 段" % (token[:8], turn, len(segs)),
              flush=True)

        if guest.is_over(token):
            chat_history = chat_history + [
                {"role": "assistant", "content": "—— %s" % guest.ending_line()},
            ]
            yield (gr.update(interactive=False), chat_history, gr.update(), "",
                   gr.update(visible=True), gr.update(value=""))
            return
    except Exception as e:
        print("[游客] 出错：%s" % e, flush=True)
        traceback.print_exc()
        chat_history = chat_history + [
            {"role": "assistant", "content": "⚠️ 她那边断了一下，再说一次。"}]

    yield "", chat_history, gr.update(), "", *KEEP


def clear_chat():
    return [], str(uuid.uuid4())
