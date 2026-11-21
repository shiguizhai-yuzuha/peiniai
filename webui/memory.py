"""记室 · 记忆面板：模式、预览、增删、固定。

负责
  · 两套记忆模式的保存与预览
  · 单条记忆的删除、固定
  · 偏好保存（昵称/风格/安静时段）
  · 她的主页打开

不负责
  · 不做检索算法（那是 core/recall）"""
# 名字　记室 —— 古代掌书记的官。记忆就是她把你说的话记下来。


import gradio as gr

from config import DEFAULT_PERSONA
from config import MEMORY_PINNED_MAX
from config import PERSONAS
from db import repository as repo

from webui.helpers import _valid_hhmm
from webui.render import render_profile


_SEP = "\x1f"


# 记忆分组顺序（跟角色顺序一致）
MEM_ORDER = list(PERSONAS.keys())


def _mem_split(user_id):
    """把记忆按角色拆开。

    返回 (全局列表, {角色: 列表})，每项是 (显示文字, persona+key)。
    全局记忆单独一组，因为它被所有角色共享。
    """
    shared = []
    per = {p: [] for p in MEM_ORDER}
    if not user_id:
        return shared, per

    for m in repo.list_all_memories(user_id):
        label = ("🔒 " if m["pinned"] else "") + m["value"]
        val = m["persona"] + _SEP + m["key"]
        if m["persona"] == "__global__":
            shared.append((label, val))
        elif m["persona"] in per:
            per[m["persona"]].append((label, val))
    return shared, per


def _pin_stat(user_id):
    """「已锁 N / 上限」——超出的话那几条根本进不了她的记忆。"""
    if not user_id:
        return ""
    n = sum(1 for m in repo.list_all_memories(user_id) if m.get("pinned"))
    if n <= MEMORY_PINNED_MAX:
        return f"**已锁 {n} / {MEMORY_PINNED_MAX}**"
    over = n - MEMORY_PINNED_MAX
    return (f"**已锁 {n} / {MEMORY_PINNED_MAX}**　"
            f"⚠️ 超出 {over} 条，这 {over} 条不会出现在她的记忆里")


def _mem_refresh(user_id):
    """返回：统计文字 + 所有记忆分组的新选项（全局 + MEM_ORDER）。"""
    shared, per = _mem_split(user_id)
    return [gr.update(value=_pin_stat(user_id))] + [
        gr.update(choices=shared, value=[])
    ] + [
        gr.update(choices=per[p], value=[]) for p in MEM_ORDER
    ]


def _split_value(v):
    if not v or _SEP not in str(v):
        return (None, None)
    p, k = str(v).split(_SEP, 1)
    return (p, k)


def do_save_memory_mode(user_id, choice):
    """保存"她的记性"。choice 是界面上的中文选项。"""
    if not user_id:
        return "先登录。"
    try:
        from core import memory_state as _ms
        _ms.ensure_schema()
        mode = _ms.MODE_MIXED if choice == "像人" else _ms.MODE_PURE
        _ms.set_user_mode(user_id, mode)
        _label = "像人（会记不清一些事，但记得重要的）" if mode == _ms.MODE_MIXED \
            else "记得细（什么细节都记得，但偶尔像数据库）"
        return "已保存：**%s**。下一句开始生效。" % _label
    except Exception as e:
        return "保存失败：%s" % e


def do_preview_memory(user_id, persona):
    """拿他上一句话，把两种模式的注入段并排打出来。"""
    if not user_id:
        return "先登录。", "先登录。"
    try:
        from core import recall as _recall
        from core import memory_state as _ms
        from core import daily as _daily
        from db import repository as _repo

        msgs = _repo.get_recent_messages(user_id, persona, limit=20) or []
        last = ""
        for m in reversed(msgs):
            if m.get("role") == "user":
                last = m.get("content") or ""
                break
        if not last.strip():
            return "还没有你说过的话，先去聊两句。", "还没有你说过的话，先去聊两句。"

        _kws = _recall.keywords(last)
        hits = _recall.search(user_id, persona, last, exclude_days=2,
                              limit=8, drop_words=(persona, "小光", "师姐"))
        if not hits:
            return ("上一句：**%s**\n\n没有检索到旧记录。" % last,
                    "上一句：**%s**\n\n没有检索到旧记录。" % last)

        try:
            _diary = _daily.recent(user_id, persona, days=2) or []
        except Exception:
            _diary = []
        _dd = set(str(d)[:10] for d, _s in _diary)

        try:
            _pinned = _repo.get_memories_pinned(user_id, persona, limit=50) or []
            _perm = [x.get("value") for x in _pinned]
        except Exception:
            _perm = []

        def _fmt(mode):
            txt, info = _ms.render(user_id, persona, hits, mode=mode,
                                   permanent_values=_perm, diary_days=_dd,
                                   recall_kws=_kws)
            head = "```\n%s\n```" % _ms.log_line(info)
            body = txt if txt else "（空）"
            return "**%s**\n\n%s\n\n```\n%s\n```" % (
                "pure · 原样" if mode == _ms.MODE_PURE else "mixed · 三档",
                head, body.strip())

        return _fmt(_ms.MODE_PURE), _fmt(_ms.MODE_MIXED)
    except Exception as e:
        return "出错：%s" % e, "出错：%s" % e


def do_save_prefs(user_id, style, quiet_on, start, end):
    if not user_id:
        return "请先登录"
    repo.set_user_pref(user_id, "reply_style", style or "normal")
    if quiet_on:
        s = (start or "").strip()
        e = (end or "").strip()
        if not (_valid_hhmm(s) and _valid_hhmm(e)):
            return "时间要写成 `23:30` 这种格式"
        repo.set_user_pref(user_id, "quiet_start", s)
        repo.set_user_pref(user_id, "quiet_end", e)
    else:
        repo.set_user_pref(user_id, "quiet_start", "")
        repo.set_user_pref(user_id, "quiet_end", "")
    return "✅ 已保存"


def do_mem_action(user_id, action, *groups):
    """锁定 / 解锁 / 忘掉。groups 是所有分组的勾选结果，合并后统一处理。"""
    if not user_id:
        return ("请先登录", *_mem_refresh(user_id))

    sel = []
    for g in groups:
        sel.extend(g or [])
    if not sel:
        return ("先勾选几条", *_mem_refresh(user_id))

    n = 0
    for v in sel:
        p, k = _split_value(v)
        if not p:
            continue
        if action == "lock":
            repo.set_memory_pinned(user_id, p, k, 1)
        elif action == "unlock":
            repo.set_memory_pinned(user_id, p, k, 0)
        elif action == "delete":
            repo.delete_memory_any(user_id, p, k)
        n += 1

    word = {"lock": "锁定", "unlock": "取消锁定", "delete": "忘掉"}.get(action, "处理")
    return (f"✅ 已{word} {n} 条", *_mem_refresh(user_id))


def do_pin(user_id, target, text):
    """手动让她记住一件事。存进指定角色（或所有角色），锁定，永不被裁剪。"""
    if not user_id:
        return ("请先登录", *_mem_refresh(user_id))
    t = (text or "").strip()
    if not t:
        return ("写点什么再点保存", *_mem_refresh(user_id))

    persona = "__global__" if target == "所有角色" else (target or DEFAULT_PERSONA)
    key = "lock:" + t[:20]
    repo.upsert_memory(user_id, persona, key, t[:120], priority=9)
    repo.set_memory_pinned(user_id, persona, key, 1)
    return ("✅ 记住了，这条不会被忘掉", *_mem_refresh(user_id))


def do_set_mode(user_id, mode, persona=""):
    """切换关系模式：恋爱 / 陪伴。"""
    try:
        from core import mode as mode_mod
        m = "companion" if str(mode).lower() in ("companion", "陪伴") else "romance"
        mode_mod.set_mode(user_id, m, persona or "")
        try:
            from db import repository as repo
            repo.add_milestone(user_id, "*", "mode_" + m, "关系改成" + ("陪伴" if m == "companion" else "恋爱"))
        except Exception:
            pass
        if m == "companion":
            return "已切换：陪伴。她记得你，只是不再用恋人的方式说话。"
        return "已切换：恋爱。关系从今天重新开始推进。"
    except Exception as e:
        return "切换失败：%s" % e


def get_mode_label(user_id, persona=""):
    try:
        from core import mode as mode_mod
        return "陪伴" if mode_mod.get_mode(user_id, persona or "") == "companion" else "恋爱"
    except Exception:
        return "恋爱"


def open_profile(user_id, persona=None):
    persona = persona or DEFAULT_PERSONA
    style = repo.get_user_pref(user_id, "reply_style", "normal") if user_id else "normal"
    qs = repo.get_user_pref(user_id, "quiet_start", "") if user_id else ""
    qe = repo.get_user_pref(user_id, "quiet_end", "") if user_id else ""
    # 「她的记性」单选框要显示已保存的值，不然会永远停在默认那个
    try:
        from core import memory_state as _ms
        _mm = "像人" if _ms.resolve_mode(user_id) == _ms.MODE_MIXED else "记得细"
    except Exception:
        _mm = "像人"
    return (
        gr.update(visible=False),          # chat_group
        gr.update(visible=True),           # profile_group
        render_profile(user_id),           # profile_html
        gr.update(value=style),            # style_radio
        gr.update(value=bool(qs and qe)),  # quiet_on
        gr.update(value=qs or "23:30"),    # quiet_start
        gr.update(value=qe or "07:00"),    # quiet_end
        gr.update(value=_mm),              # mem_radio
        *_mem_refresh(user_id),            # 全局 + 6 个角色的记忆分组
        gr.update(value=persona),          # pin_target 默认当前角色
    )
