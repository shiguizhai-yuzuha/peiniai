"""帘 · 背景：设置与恢复。

负责
  · 上传背景图、存下来
  · 恢复默认

不负责
  · 不做审核（那是 审核背景.py）"""
# 名字　帘 —— 挂上去、收起来。她身后那片景。


import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from db import repository as repo

from webui.helpers import _is_vip


def do_set_bg(user_id, persona, filepath):
    """换背景：压缩 → 存盘 → 入待审。"""
    if not user_id:
        return "⚠️ 请先登录。"
    if not _is_vip(user_id):
        return "⚠️ 换背景现在只对老友开放。\n\n（每一张我要人工看一遍，人多了看不过来。）"
    if not filepath:
        return "⚠️ 先选一张图。"
    if not persona:
        return "⚠️ 先选一个角色。"

    try:
        import uuid as _uuid
        from PIL import Image as _Image

        im = _Image.open(filepath).convert("RGB")
        w, h = im.size
        MAX_W = 1080
        if w > MAX_W:
            im = im.resize((MAX_W, int(h * MAX_W / w)), _Image.LANCZOS)

        d = os.path.join(_ROOT, "static", "user_bg")
        os.makedirs(d, exist_ok=True)

        # 文件名带 user_id，防撞
        safe_persona = "".join(ch for ch in str(persona) if ch.isalnum() or ch in "_-")
        fname = "%s_%s_%s.jpg" % (str(user_id)[:16], safe_persona, _uuid.uuid4().hex[:6])
        out = os.path.join(d, fname)
        im.save(out, "JPEG", quality=78, optimize=True, progressive=True)

        size_kb = os.path.getsize(out) / 1024

        # 旧文件清掉
        old = repo.delete_user_bg(user_id, persona)
        if old and os.path.exists(old):
            try:
                os.remove(old)
            except Exception:
                pass

        repo.set_user_bg(user_id, persona, out, status="pending")
        print("[换背景] user=%s persona=%s %.0fKB → pending" % (str(user_id)[:8], persona, size_kb),
              flush=True)
        return ("✅ 已经换成这张了。\n\n"
                "**切到「%s」就能看到。**" % persona)
    except Exception as e:
        print("[换背景] 失败：%s" % e, flush=True)
        return "⚠️ 换背景失败：%s" % e


def do_reset_bg(user_id, persona):
    if not user_id:
        return "⚠️ 请先登录。"
    old = repo.delete_user_bg(user_id, persona)
    if old and os.path.exists(old):
        try:
            os.remove(old)
        except Exception:
            pass
    print("[换背景] user=%s persona=%s 恢复默认" % (str(user_id)[:8], persona), flush=True)
    return "✅ 「%s」已经用回原来的背景。" % persona
