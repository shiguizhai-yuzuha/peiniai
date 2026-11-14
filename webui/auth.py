"""叩门 · 登录注册：账号、免登录试聊、游客转正。

负责
  · 注册 / 登录 / 登出
  · 免登录试聊的 token
  · 游客转正
  · 改密码

不负责
  · 不校验密码强度（那是 core/auth）"""
# 名字　叩门 —— 先敲门，里头应了声，才进得来。


import uuid

import gradio as gr

from config import DEFAULT_PERSONA
from config import OPENINGS
from core.auth import hash_password
from core.auth import validate_password
from core.auth import validate_username
from core.auth import verify_password
from db import repository as repo
from services import guest

from webui.chat import load_history, opening_history
from webui.render import get_bg_style, render_relationship


def do_register(username, password, password2, invite_code):
    if password != password2:
        return None, "两次密码不一致", gr.update(visible=True), gr.update(visible=False), []
    ok, msg = validate_username(username)
    if not ok:
        return None, msg, gr.update(visible=True), gr.update(visible=False), []
    ok, msg = validate_password(password)
    if not ok:
        return None, msg, gr.update(visible=True), gr.update(visible=False), []

    user_id, err = repo.register_user(username, password, invite_code)
    if err:
        return None, err, gr.update(visible=True), gr.update(visible=False), []

    return user_id, f"✅ 注册成功，欢迎 {username}", gr.update(visible=False), gr.update(visible=True), opening_history(DEFAULT_PERSONA)


def do_login(username, password):
    user_id, err = repo.login_user(username, password)
    if err:
        return (
            None, err,
            gr.update(visible=True), gr.update(visible=False),
            [],
            DEFAULT_PERSONA,
            get_bg_style(is_login=True),
            "",
        )

    history = load_history(user_id, DEFAULT_PERSONA)
    if not history:
        history = opening_history(DEFAULT_PERSONA)
    rel_html = render_relationship(user_id, DEFAULT_PERSONA)

    return (
        user_id,
        f"✅ 欢迎回来，{username}",
        gr.update(visible=False),
        gr.update(visible=True),
        history,
        DEFAULT_PERSONA,
        get_bg_style(DEFAULT_PERSONA),
        rel_html,
    )


def do_logout():
    return (
        None, "已退出登录",
        gr.update(visible=True),
        gr.update(visible=False),
        [],
        DEFAULT_PERSONA,
        get_bg_style(is_login=True),
        "",
    )


def do_guest(request: gr.Request):
    """开一个游客会话。不进数据库，不建账号。

    返回和 do_login 一样的八元组，界面不动。
    """
    ip = "0.0.0.0"
    try:
        ip = request.client.host or "0.0.0.0"
    except Exception:
        pass

    token, err = guest.open_session(ip)
    if not token:
        wait = guest.ip_wait_seconds(ip)
        mins = max(1, int(wait / 60))
        return (
            None,
            "她已经见过一个人了。%d 分钟后再来，或者直接注册。" % mins,
            gr.update(visible=True), gr.update(visible=False),
            [], DEFAULT_PERSONA, get_bg_style(is_login=True), "",
            None,
            gr.update(),
        )

    openings = OPENINGS.get(guest.GUEST_PERSONA, [])
    history = []
    for line in openings:
        history.append({"role": "assistant", "content": line})
        guest.append(token, "assistant", line)

    print("[游客] 开 %s ip=%s 轮数=%d" % (token[:8], ip, guest.GUEST_TURNS),
          flush=True)

    return (
        None,                      # user_id 保持空，别的面板不会去查库
        "先说几句。说满 %d 轮，她就要跟你说一件事。" % guest.GUEST_TURNS,
        gr.update(visible=False),
        gr.update(visible=True),
        history,
        guest.GUEST_PERSONA,
        get_bg_style(guest.GUEST_PERSONA),
        "",
        token,                     # 第 9 个：游客凭证
        gr.update(value=guest.GUEST_PERSONA),   # 第 10 个：顶部的角色下拉
    )


def do_keep(username, password, token):
    """游客转正：注册 + 继承那十轮。

    邀请码用内部码 GUEST，用户不用输。
    """
    def _fail(msg):
        return (gr.update(), gr.update(), gr.update(), gr.update(),
                gr.update(), gr.update(), msg)

    if not token:
        return _fail("⚠️ 这段对话过期了，刷新页面重来。")

    username = (username or "").strip()
    if len(username) < 2:
        return _fail("用户名至少 2 个字。")
    if len(password or "") < 6:
        return _fail("密码至少 6 位。")

    user_id, err = repo.register_user(username, password, "GUEST")
    if err:
        return _fail("⚠️ " + err)

    sess = guest.close(token)
    persona = guest.GUEST_PERSONA
    history = sess.get("history", []) or []

    sid = str(uuid.uuid4())
    chat_history = []
    said = []

    for h in history:
        role = h.get("role")
        content = (h.get("content") or "").strip()
        if not content:
            continue
        try:
            repo.save_message(sid, user_id, persona, role, content)
        except Exception as e:
            print("[转正] 写消息失败：%s" % e, flush=True)
        chat_history.append({"role": role, "content": content})
        if role == "user" and 2 <= len(content) <= 60:
            said.append(content)

    for i, s in enumerate(said[:3]):
        try:
            repo.upsert_memory(user_id, persona, "guest_%d" % (i + 1),
                               s[:40], priority=7)
        except Exception as e:
            print("[转正] 写记忆失败：%s" % e, flush=True)

    for line in ("……你想起来了。", "我刚才差点把你叫什么忘了。", "现在不会了。"):
        chat_history.append({"role": "assistant", "content": line})
        try:
            repo.save_message(sid, user_id, persona, "assistant", line)
        except Exception:
            pass

    print("[转正] %s 继承 %d 条，记忆 %d 条"
          % (username, len(history), min(3, len(said))), flush=True)

    return (
        user_id,
        gr.update(visible=True),                 # chat_group
        gr.update(visible=False),                # guest_save_group
        chat_history,                            # chatbot
        gr.update(value=""),                     # guest_end_md
        render_relationship(user_id, persona),   # relationship_html
        "✅ 好了。她记得。",                      # guest_save_msg
    )


def do_change_password(user_id, old_pwd, new_pwd, new_pwd2):
    if not user_id:
        return "请先登录"
    user = repo.get_or_create_user(user_id) or {}
    if not verify_password(old_pwd or "", user.get("password_hash") or ""):
        return "❌ 旧密码不对"
    ok, msg = validate_password(new_pwd or "")
    if not ok:
        return f"❌ {msg}"
    if new_pwd != new_pwd2:
        return "❌ 两次新密码不一致"
    repo.update_password(user_id, hash_password(new_pwd))
    return "✅ 密码已修改，下次用新密码登录"
