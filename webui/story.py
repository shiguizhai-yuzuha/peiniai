"""话本 · 剧情：列表、启动、刷新、播放页。

负责
  · 剧情列表 markdown
  · 构造剧情人设
  · 启动与刷新后台任务
  · /story/{sid} 播放页

不负责
  · 不跑剧情任务（那是 services/story_jobs）"""
# 名字　话本 —— 说书人的底本。一页一页，讲到哪算哪。


import gradio as gr

from config import DEFAULT_PERSONA
from config import GALGAME_ENABLED
from core import personas
from db import repository as repo
from galgame import geo as ggeo
from galgame import player as gplayer
from services import story_jobs


# 目的地固定杭州。这里列的是"出发地"候选，第一项是自动。
STORY_DEST = "杭州"


STORY_AUTO = "自动（按 IP）"


STORY_ORIGINS = [STORY_AUTO, "新艾利都", "温州", "金华", "宁波", "上海",
                 "苏州", "南京", "合肥", "福州", "南昌", "济南", "北京", "广州"]


def _story_list_md(user_id):
    rows = repo.list_stories(user_id, limit=10)
    if not rows:
        return "_还没有。_"
    out = []
    for r in rows:
        st = r.get("status")
        title = r.get("title") or "（未命名）"
        line = "· **%s**　%s → %s　%s" % (
            title, r.get("origin") or "?", r.get("city") or "?", story_jobs.status_line(r))
        if st == "done":
            line += "　[看](/%s)" % ("story/" + r["id"])
        out.append(line)
    return "\n".join(out)


def build_story_profile(user_id, persona):
    """从记忆里拼一个画像。只读，绝不写库。

    拿的是：名字、喜好、厌恶、最近状态、情绪、态度、好感、信任。
    """
    prof = {"name": "", "likes": [], "dislikes": [], "state": "", "mood": "",
            "attitude": "", "intimacy": 30, "trust": 50}
    try:
        mems = repo.get_memories_all(user_id, persona, limit=120)
    except Exception:
        mems = []

    for m in mems or []:
        k = str(m.get("key") or "")
        v = str(m.get("value") or "").strip()
        if not v:
            continue
        if k == "name" and not prof["name"]:
            prof["name"] = v[:20]
        elif k.startswith("like:") and len(prof["likes"]) < 8:
            prof["likes"].append(v[:20])
        elif k.startswith("dislike:") and len(prof["dislikes"]) < 6:
            prof["dislikes"].append(v[:20])
        elif k == "daily_state" and not prof["state"]:
            prof["state"] = v[:40]
        elif k == "mood" and not prof["mood"]:
            prof["mood"] = v[:30]
        elif k == "attitude" and not prof["attitude"]:
            prof["attitude"] = v[:40]

    try:
        st = repo.get_character_state(user_id, persona) or {}
        prof["intimacy"] = float(st.get("intimacy") or 30)
        prof["trust"] = float(st.get("trust") or 50)
    except Exception:
        pass

    return prof


def do_story_start(user_id, origin_choice, persona=None, request: gr.Request = None):
    """开始生成。目的地固定杭州，出发地按选择或 IP。人设和画像来自当前角色。"""
    if not GALGAME_ENABLED:
        # 2026-11-01 下架。入口已隐藏，这里再拦一道，防止旧页面或直接调用。
        return "这个功能已经下架了。", "_已下架。_"
    if not user_id:
        return "⚠️ 请先登录。", ""

    city = STORY_DEST
    persona = persona or DEFAULT_PERSONA

    # 只读：她的说话方式 + 她记得的你
    try:
        character_text = personas.get_prompt(persona, user_id)
    except Exception as e:
        print("[剧情] 取人设失败：%s" % e, flush=True)
        character_text = None
    profile = build_story_profile(user_id, persona)
    print("[剧情] 画像 %s" % profile, flush=True)

    # 用户指定了就用他选的；选"自动"才去查 IP
    if origin_choice and origin_choice != STORY_AUTO:
        origin = origin_choice
        print("[剧情] 出发地（手动）：%s" % origin, flush=True)
    else:
        try:
            ip = ""
            if request is not None:
                ip = ggeo.client_ip_from_headers(dict(request.headers or {}))
                if not ip and getattr(request, "client", None):
                    ip = request.client.host or ""
            origin = ggeo.locate(ip, destination=city)
            print("[剧情] 定位 %s → 出发地 %s" % (ip or "(空)", origin), flush=True)
        except Exception as e:
            print("[剧情] 定位失败，用新艾利都：%s" % e, flush=True)
            origin = "新艾利都"

    sid, err = story_jobs.start(user_id, city=city, origin=origin,
                                profile=profile, character_text=character_text)
    if not sid:
        return "⚠️ %s" % err, _story_list_md(user_id)

    who = personas.display_name(persona) if hasattr(personas, "display_name") else persona
    msg = ("✅ 开始生成。\n\n"
           "**%s → %s**\n\n"
           "**和谁：%s**（用的她记得的你：%s）\n\n"
           "大约 5 分钟。点「刷新」看进度，好了会有「看」。"
           % (origin, city, who,
              "、".join(profile.get("likes") or []) or "还没什么印象"))
    return msg, _story_list_md(user_id)


def do_story_refresh(user_id):
    if not user_id:
        return "⚠️ 请先登录。", ""
    return story_jobs.quota_line(user_id), _story_list_md(user_id)


def _story_page(sid: str):
    """把一份生成好的剧情渲染成网页。"""
    from fastapi.responses import HTMLResponse

    row = repo.get_story(sid)
    if not row:
        return HTMLResponse("<meta charset='utf-8'><h2>找不到这一份</h2>", status_code=404)
    if row.get("status") != "done":
        msg = story_jobs.status_line(row)
        return HTMLResponse(
            "<meta charset='utf-8'><meta http-equiv='refresh' content='4'>"
            "<body style='background:#14171c;color:#e8e6e3;font-family:sans-serif;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
            "<div style='text-align:center'><h2 style='font-weight:400'>%s</h2>"
            "<p style='color:#8a9099;font-size:14px'>这个页面每 4 秒自动刷新</p></div></body>" % msg,
            status_code=200,
        )

    try:
        import json as _json
        with open(row["file"], encoding="utf-8") as f:
            data = _json.load(f)
        title = "%s · %s" % (row.get("origin") or "", row.get("city") or "")
        return HTMLResponse(gplayer.render_html(data, title))
    except Exception as e:
        return HTMLResponse("<meta charset='utf-8'><h2>读不出来：%s</h2>" % e, status_code=500)
