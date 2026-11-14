"""拓 · 导出：txt、纪念册、全部。

负责
  · 导出面板刷新
  · 三种导出

不负责
  · 不生成内容（那是 services/export + keepsake）"""
# 名字　拓 —— 从碑上拓下来。原件留在原处，拓片带走。


import gradio as gr

from db import repository as repo
from services import billing
from services import keepsake as gkeep

from webui.helpers import _today
from webui.persona import _my_personas


def do_export_refresh(user_id):
    if not user_id:
        return "⚠️ 请先登录。", gr.Dropdown(choices=[], value=None)
    ps = _my_personas(user_id)
    if not ps:
        return "还没有可以带走的对话。先去聊几句。", gr.Dropdown(choices=[], value=None)
    return ("选一个角色，或者导出全部。", gr.Dropdown(choices=ps, value=ps[0]))


def do_export_txt(user_id, persona):
    """原始聊天记录，免费。"""
    if not user_id:
        return "⚠️ 请先登录。"
    if not persona:
        return "⚠️ 先选一个角色。"
    try:
        txt = gkeep.render_txt(user_id, persona)
        path, name = gkeep.save("txt", txt, "txt",
                                  stem="陪你AI_聊天记录_%s_%s" % (persona, _today()))
        return ("✅ 好了：**[点这里下载](%s)**　（%s，%d 字）\n\n"
                "下载不了就试这个：[强制下载](%s)"
                % ("/keepsake/" + name, persona, len(txt),
                   "/keepsake/dl/" + name))
    except Exception as e:
        return "⚠️ 导出失败：%s" % e


def do_export_book(user_id, persona):
    """纪念册，一个角色 3 元，vip 免费。"""
    if not user_id:
        return "⚠️ 请先登录。"
    if not persona:
        return "⚠️ 先选一个角色。"
    try:
        user = repo.get_or_create_user(user_id)
        is_vip = (user.get("role") == "vip")
        if not is_vip:
            if not billing.has_balance(user_id, gkeep.PRICE_ONE):
                return "⚠️ 余额不够，这一份要 %.0f 元。" % gkeep.PRICE_ONE
            billing.charge_yuan(user_id, gkeep.PRICE_ONE)

        html_text = gkeep.render_html(user_id, [persona])
        if not html_text:
            if not is_vip:
                repo.update_balance(user_id, gkeep.PRICE_ONE)
            return "⚠️ 这个角色还没有足够的对话。"
        path, name = gkeep.save("html", html_text, "html",
                                  stem="%s_纪念册_%s" % (persona, _today()))
        tip = "（老友免费）" if is_vip else "（扣 %.0f 元）" % gkeep.PRICE_ONE
        return ("✅ 纪念册好了 %s\n\n"
                "**[点这里打开](%s)**　|　**[下载文件](%s)**\n\n"
                "手机直接截长图存下来。电脑上也能 Ctrl+P 存 PDF。"
                % (tip, "/keepsake/" + name, "/keepsake/dl/" + name))
    except Exception as e:
        return "⚠️ 生成失败：%s" % e


def do_export_all(user_id):
    """全部角色，9.9 元，vip 免费。"""
    if not user_id:
        return "⚠️ 请先登录。"
    try:
        ps = _my_personas(user_id)
        if not ps:
            return "⚠️ 还没有可以带走的对话。"
        user = repo.get_or_create_user(user_id)
        is_vip = (user.get("role") == "vip")
        if not is_vip:
            if not billing.has_balance(user_id, gkeep.PRICE_ALL):
                return "⚠️ 余额不够，全部要 %.1f 元。" % gkeep.PRICE_ALL
            billing.charge_yuan(user_id, gkeep.PRICE_ALL)

        html_text = gkeep.render_html(user_id, ps)
        if not html_text:
            if not is_vip:
                repo.update_balance(user_id, gkeep.PRICE_ALL)
            return "⚠️ 没有内容。"
        path, name = gkeep.save("html", html_text, "html",
                                  stem="陪你AI_纪念册_全部角色_%s" % _today())
        tip = "（老友免费）" if is_vip else "（扣 %.1f 元）" % gkeep.PRICE_ALL
        return ("✅ 全部 %d 个角色都在里面 %s\n\n"
                "**[点这里打开](%s)**　|　**[下载文件](%s)**\n\n"
                "手机上直接截长图。电脑上也能 Ctrl+P 存 PDF。"
                % (len(ps), tip, "/keepsake/" + name, "/keepsake/dl/" + name))
    except Exception as e:
        return "⚠️ 生成失败：%s" % e
