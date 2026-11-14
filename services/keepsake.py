# -*- coding: utf-8 -*-
"""纪念册 —— 把这个带走

免费档：原始聊天记录 .txt
付费档：排版好的纪念册（一个角色 3 元，全部 9.9 元，vip 免费）

为什么纪念册要收费：它是产品，不是数据。
为什么 .txt 免费：那是用户自己的东西，收费只会被骂。

渲染方式是纯 HTML（浏览器打印成 PDF），不调模型，成本为零。
"""

import html
import io
import os
import sqlite3
from datetime import datetime

from db import repository as repo

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "keepsakes")

PRICE_ONE = 3.0      # 一个角色
PRICE_ALL = 9.9      # 全部角色


# ============ 数据 ============

def _conn():
    c = sqlite3.connect(os.path.join(BASE, "love_bot.db"))
    c.row_factory = sqlite3.Row
    return c


def _one_memory_list(c, uid, persona):
    return [dict(r) for r in c.execute(
        "SELECT key, value, priority FROM memories "
        "WHERE user_id=? AND persona=? ORDER BY priority DESC, updated_at DESC LIMIT 30",
        (uid, persona))]


def _milestones(c, uid, persona):
    try:
        return [dict(r) for r in c.execute(
            "SELECT title, detail, created_at FROM milestones "
            "WHERE user_id=? AND persona=? AND title NOT LIKE 'hidden:%' "
            "ORDER BY created_at", (uid, persona))]
    except Exception:
        return []


def _diaries(c, uid, persona, limit=10):
    try:
        return [dict(r) for r in c.execute(
            "SELECT day, summary FROM daily_summaries "
            "WHERE user_id=? AND persona=? ORDER BY day DESC LIMIT ?",
            (uid, persona, limit))]
    except Exception:
        return []


def _best_lines(c, uid, persona, n=6):
    """挑几句最重的。用户说得最长的几轮 + 她的回应。"""
    try:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE user_id=? AND persona=? AND role='user' AND LENGTH(content) >= 12 "
            "ORDER BY LENGTH(content) DESC LIMIT ?", (uid, persona, n)).fetchall()
        out = []
        for r in rows:
            nxt = c.execute(
                "SELECT content FROM messages "
                "WHERE user_id=? AND persona=? AND role='assistant' AND id > "
                "(SELECT id FROM messages WHERE user_id=? AND persona=? AND content=? ORDER BY id LIMIT 1) "
                "ORDER BY id LIMIT 1", (uid, persona, uid, persona, r["content"])).fetchone()
            out.append({
                "text": r["content"],
                "reply": (nxt[0] if nxt else ""),
                "date": str(r["created_at"] or "")[:10],
            })
        return out
    except Exception:
        return []


def _first_date(c, uid, persona):
    try:
        r = c.execute("SELECT MIN(created_at) FROM messages WHERE user_id=? AND persona=?",
                      (uid, persona)).fetchone()
        return str(r[0] or "")[:10] if r and r[0] else ""
    except Exception:
        return ""


def _stage_of(st):
    """关系阶段是从好感和告白状态算出来的，库里那一列经常是空的。"""
    try:
        from core import relationship as _rel
        return _rel.get_stage(float(st.get("intimacy") or 0),
                              bool(st.get("confessed_at")))
    except Exception:
        return st.get("relationship_stage") or "刚认识"


def build_data(user_id, persona):
    """把纪念册需要的所有东西拼起来。"""
    c = _conn()
    try:
        st = repo.get_character_state(user_id, persona) or {}
        first = _first_date(c, user_id, persona)
        days = 0
        if first:
            try:
                d0 = datetime.strptime(first, "%Y-%m-%d")
                days = max(1, (datetime.now() - d0).days + 1)
            except Exception:
                days = 0

        n_msg = c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND persona=?",
                          (user_id, persona)).fetchone()[0]
        n_days = c.execute(
            "SELECT COUNT(DISTINCT DATE(created_at,'+8 hours')) FROM messages "
            "WHERE user_id=? AND persona=?", (user_id, persona)).fetchone()[0]

        return {
            "persona": persona,
            "first_date": first,
            "days": days,
            "intimacy": round(float(st.get("intimacy") or 0), 1),
            "trust": round(float(st.get("trust") or 0), 1),
            "stage": _stage_of(st),
            "n_msg": n_msg,
            "n_days": n_days,
            "memories": _one_memory_list(c, user_id, persona),
            "milestones": _milestones(c, user_id, persona),
            "diaries": _diaries(c, user_id, persona),
            "lines": _best_lines(c, user_id, persona),
        }
    finally:
        c.close()


def list_personas(user_id):
    """他用过哪些角色，各自有多少条消息。"""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT persona, COUNT(*) n, MAX(created_at) last "
            "FROM messages WHERE user_id=? AND persona NOT LIKE 'custom:%' "
            "GROUP BY persona HAVING n >= 4 ORDER BY n DESC", (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


# ============ 原始 txt（免费） ============

def render_txt(user_id, persona):
    c = _conn()
    try:
        d = build_data(user_id, persona)
        rows = c.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE user_id=? AND persona=? ORDER BY id", (user_id, persona)).fetchall()
    finally:
        c.close()

    L = []
    L.append("=" * 46)
    L.append("陪你 AI · 聊天记录")
    L.append("角色：%s" % personal_name(persona))
    L.append("从 %s 开始，共 %d 天，%d 条消息" % (d["first_date"] or "?", d["n_days"], d["n_msg"]))
    L.append("导出时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    L.append("=" * 46)
    L.append("")
    cur_day = None
    for r in rows:
        day = str(r["created_at"] or "")[:10]
        if day != cur_day:
            cur_day = day
            L.append("")
            L.append("---------- %s ----------" % day)
        who = "你" if r["role"] == "user" else personal_name(persona)
        txt = str(r["content"] or "").replace("<msg>", "\n")
        L.append("%s：%s" % (who, txt))
    L.append("")
    L.append("=" * 46)
    L.append("这些是你的记录。想带走就带走。")
    return "\n".join(L)


def personal_name(persona):
    return str(persona or "").replace("custom:", "") or "她"


# ============ 纪念册 HTML（付费） ============

def _cover_image(persona, max_w=760, quality=82):
    """把角色的立绘压小、转 base64，直接内嵌进 HTML。

    为什么内嵌：纪念册发出去是一份独立文件，不能依赖站点的图。
    为什么压小：原图 2.4MB，base64 之后 3MB，手机打不开。
    """
    import base64
    try:
        from config import CHARACTER_BACKGROUNDS
        rel = CHARACTER_BACKGROUNDS.get(persona)
        if not rel:
            return ""
        path = os.path.join(BASE, rel.replace("/", os.sep))
        # 优先用竖版（封面是竖的），没有就用横版
        root, ext = os.path.splitext(path)
        v = root + "_v" + ext
        if os.path.isfile(v):
            path = v
        if not os.path.isfile(path):
            return ""

        from PIL import Image
        im = Image.open(path).convert("RGB")
        w, h = im.size
        # 竖版太长就裁掉下面，留上半身
        if h > w * 1.45:
            im = im.crop((0, 0, w, int(w * 1.45)))
            w, h = im.size
        if w > max_w:
            im = im.resize((max_w, int(h * max_w / w)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return "data:image/jpeg;base64," + b64
    except Exception as e:
        print("[纪念册] 立绘处理失败：%s" % e, flush=True)
        return ""


def _esc(s):
    return html.escape(str(s or ""))


def _card(title, body):
    if not str(body or "").strip():
        return ""
    return '<section><h2>%s</h2>%s</section>' % (_esc(title), body)


def render_html(user_id, personas=None):
    """personas 为 None 表示全部角色。"""
    if not personas:
        personas = [x["persona"] for x in list_personas(user_id)]
    if not personas:
        return None

    blocks = []
    for p in personas:
        d = build_data(user_id, p)
        name = personal_name(p)

        # 封面（有立绘就压在上面，没有就是纯文字）
        _img = _cover_image(p)
        _style = (' style="background-image:url(%s)"' % _img) if _img else ""
        head = (
            '<div class="cover%s"%s>'
            '<div class="cv-mask"></div>'
            '<div class="cv-in">'
            '<div class="cv-name">%s</div>'
            '<div class="cv-days">%d 天</div>'
            '<div class="cv-sub">%d 条消息 · %d 天里聊过</div>'
            '</div>'
            '</div>' % (" has-img" if _img else "", _style,
                        _esc(name), d["days"], d["n_msg"], d["n_days"])
        )

        # 关系
        rel = (
            '<div class="rel">'
            '<div><b>%s</b><span>好感</span></div>'
            '<div><b>%s</b><span>信任</span></div>'
            '<div><b>%s</b><span>阶段</span></div>'
            '</div>' % (d["intimacy"], d["trust"], _esc(d["stage"] or "刚认识"))
        )

        # 关键对话
        lines_html = ""
        for x in d["lines"]:
            lines_html += (
                '<div class="talk">'
                '<div class="t-date">%s</div>'
                '<div class="t-me">%s</div>'
                '<div class="t-her">%s</div>'
                '</div>' % (_esc(x["date"]), _esc(x["text"]),
                             _esc(str(x["reply"] or "").replace("<msg>", " ")))
            )

        # 她的记忆 —— 分类挑，别堆 30 条
        _pick = {"other": [], "like": [], "dislike": [], "moment": [], "promise": []}
        for m in d["memories"]:
            k = str(m["key"])
            if k.startswith("like:"):
                _pick["like"].append(m)
            elif k.startswith("dislike:"):
                _pick["dislike"].append(m)
            elif k.startswith("moment:"):
                _pick["moment"].append(m)
            elif k.startswith("promise:"):
                _pick["promise"].append(m)
            else:
                _pick["other"].append(m)
        _chosen = (_pick["other"][:2] + _pick["like"][:5] + _pick["dislike"][:2]
                   + _pick["moment"][:6] + _pick["promise"][:3])

        mem_html = ""
        for m in _chosen:
            k = str(m["key"])
            if k.startswith(("like:", "dislike:")):
                tag = "喜欢" if k.startswith("like:") else "不喜欢"
                mem_html += '<li><em>%s</em>%s</li>' % (tag, _esc(m["value"]))
            elif k == "name":
                mem_html += '<li><em>你叫</em>%s</li>' % _esc(m["value"])
            elif k.startswith("moment:"):
                mem_html += '<li><em>记得</em>%s</li>' % _esc(m["value"])
            elif k.startswith("promise:"):
                mem_html += '<li><em>答应</em>%s</li>' % _esc(m["value"])
            elif k == "attitude":
                mem_html += '<li><em>她看你</em>%s</li>' % _esc(m["value"])

        # 日记
        diary_html = ""
        for x in reversed(d["diaries"]):
            diary_html += '<div class="diary"><div class="dd">%s</div><p>%s</p></div>' % (
                _esc(x["day"]), _esc(x["summary"]))

        # 里程碑
        ms_html = ""
        for x in d["milestones"]:
            ms_html += '<li><span>%s</span>%s</li>' % (
                _esc(str(x["created_at"] or "")[:10]), _esc(x["title"]))

        blocks.append(
            '<article class="ch">%s%s%s%s%s%s%s</article>' % (
                head, rel,
                _card("你说过的话", lines_html),
                _card("她记得的你", "<ul class='mem'>%s</ul>" % mem_html if mem_html else ""),
                _card("她写下的那些天", diary_html),
                _card("你们之间", "<ul class='ms'>%s</ul>" % ms_html if ms_html else ""),
                '<div class="foot">— 陪你 AI —</div>',
            )
        )

    title = "%s 的纪念册" % (personal_name(personas[0]) if len(personas) == 1 else "你们")
    return TPL.replace("__TITLE__", _esc(title)).replace("__BODY__", "\n".join(blocks))


TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#15171b;color:#e8e6e3;line-height:1.95;
     font:15px/1.95 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.ch{max-width:720px;margin:0 auto;padding:56px 26px 80px}
.cover{position:relative;text-align:center;padding:60px 0 44px;
       border-bottom:1px solid #2a2f36;margin-bottom:44px;overflow:hidden;border-radius:14px}
.cover.has-img{padding:0;height:520px;display:flex;align-items:flex-end;
       background-size:cover;background-position:center 22%}
.cv-mask{display:none}
.cover.has-img .cv-mask{display:block;position:absolute;inset:0;
       background:linear-gradient(180deg,rgba(10,12,15,.15) 0%,rgba(10,12,15,.55) 52%,rgba(12,14,18,.96) 100%)}
.cv-in{position:relative;z-index:2;width:100%;padding:0 24px 40px}
.cover.has-img .cv-in{padding-bottom:44px}
.cv-name{font-size:40px;font-weight:700;letter-spacing:.10em;color:#f2eee8;
       text-shadow:0 2px 16px rgba(0,0,0,.8)}
.cv-days{margin-top:14px;font-size:30px;font-weight:800;color:#ff6b6b;letter-spacing:.04em;
       text-shadow:0 2px 14px rgba(0,0,0,.85)}
.cv-sub{margin-top:10px;font-size:13px;color:#c8ccd2;letter-spacing:.12em;
       text-shadow:0 1px 8px rgba(0,0,0,.85)}
.rel{display:flex;justify-content:center;gap:38px;margin:0 0 48px;text-align:center}
.rel b{display:block;font-size:24px;color:#e8e6e3;font-weight:700}
.rel span{font-size:12px;color:#7c828b;letter-spacing:.2em}
h2{font-size:13px;font-weight:600;letter-spacing:.28em;color:#c94f4f;
   margin:48px 0 20px;padding-bottom:10px;border-bottom:1px solid #2a2f36}
.talk{margin:0 0 26px;padding-left:14px;border-left:2px solid #33383f}
.t-date{font-size:11px;color:#5d636b;letter-spacing:.14em;margin-bottom:6px}
.t-me{color:#e8e6e3}
.t-her{margin-top:6px;color:#a9b2bd;font-size:14px}
.mem,.ms{list-style:none}
.mem li,.ms li{padding:7px 0;border-bottom:1px solid #22262b;font-size:14px}
.mem em{display:inline-block;min-width:62px;margin-right:10px;font-style:normal;
        font-size:11px;letter-spacing:.14em;color:#c94f4f}
.ms li span{display:inline-block;min-width:92px;color:#5d636b;font-size:12px}
.diary{margin:0 0 26px;padding:18px 20px;background:#1b1e23;border-radius:10px}
.dd{font-size:11px;color:#5d636b;letter-spacing:.16em;margin-bottom:8px}
.diary p{font-size:14px;color:#c8ccd2}
.foot{margin-top:60px;text-align:center;font-size:12px;color:#3f444b;letter-spacing:.3em}
@media print{
  body{background:#fff;color:#222}
  .ch{max-width:none;padding:0}
  .cover{border-color:#ddd}
  .cover.has-img .cv-mask{background:linear-gradient(180deg,rgba(255,255,255,.05) 0%,rgba(255,255,255,.45) 55%,rgba(255,255,255,.93) 100%)}
  .cv-name,.cv-days,.cv-sub{text-shadow:none}
  .cv-name{color:#111}.cv-days{color:#a33}.cv-sub{color:#444}
  .cv-name{color:#111}.cv-days{color:#a33}
  h2{color:#a33;border-color:#ddd}
  .rel b{color:#111}.mem li,.ms li{border-color:#eee}
  .diary{background:#f7f7f7}.diary p{color:#333}
  .cover,.rel,section,.diary{break-inside:avoid}
  article{page-break-after:always}
}
</style></head><body>
__BODY__
</body></html>"""


# ============ 存档 ============

def ensure_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def _safe(s, n=24):
    """文件名里不能有这些字符，也不能太长。"""
    import re as _re
    s = _re.sub(r'[\\/:*?"<>|\s]+', "", str(s or ""))
    return s[:n] or "她"


def save(kind, content, ext, stem=None):
    """存一份。

    磁盘上用短码（ASCII），友好名写进同名 .name 边车。
    下载时由路由读边车，放进 Content-Disposition。
    这样 URL 永远是纯英文数字，不会有编码问题。
    """
    ensure_dir()
    import uuid
    code = uuid.uuid4().hex[:12]
    name = "%s.%s" % (code, ext)
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if stem:
        try:
            with open(path + ".name", "w", encoding="utf-8") as f:
                f.write(_safe(stem, 60))
        except Exception:
            pass
    return path, name


def display_name(name):
    """读边车，拿给人看的文件名。没有就返回 None。"""
    try:
        p = os.path.join(OUT_DIR, name + ".name")
        if os.path.isfile(p):
            s = io.open(p, encoding="utf-8").read().strip()
            if s:
                ext = os.path.splitext(name)[1]
                return s + ext
    except Exception:
        pass
    return None
