# -*- coding: utf-8 -*-
"""记忆清晰度 —— 让检索到的原文按"记不记得清"分三档呈现。

设计见 开发日志/设计_记忆清晰度_v2.txt

只有两件事：
  ① render()  把 recall 的结果按档位拼成 prompt 里那一段
  ② 加固登记   下一轮看用户有没有接话，接了才加固

不碰 recall.py，不改 FTS 索引，不做任何检索算法改动。

两种模式：
  pure   —— 与改造前的输出字节级一致（回滚用）
  mixed  —— 三档呈现

任何异常都退回 pure 的行为，绝不打断聊天。
"""
import sqlite3
from datetime import datetime

# ---- 参数 ----
# 原文的基础半衰期取 30 天，不是 7 天。
# 原因：检索本身已经把最近 2 天排除掉了，"清楚"档如果只有 7 天半衰，
#       Δ 在 2~3 天之外就全掉进模糊档，等于整体降级。
#       30 天时：Δ<13 天清楚，13~36 天模糊，>36 天只剩影子。
BASE_HALF_LIFE_DAYS = 30.0

REINFORCE_CAP = 6.0          # 最多加固到半衰期的 4 倍
CLEAR_R = 0.65
FUZZY_R = 0.30
MAX_TRACE_PER_TURN = 1       # 每轮最多 1 条"只剩影子"
TRACE_COOLDOWN_DAYS = 7      # 同一条影子 7 天内不重复
NEAR_DUP_JACCARD = 0.55      # 内容相似度超过这个，算同一件事

MODE_PURE = "pure"
MODE_MIXED = "mixed"

_HEAD = (
    "## 你翻到的旧记录\n"
    "下面是他以前说过的话，你从记录里翻出来的。\n"
    "用得上就提一句，用不上就别硬提。\n"
)
_MIXED_RULE = (
    "\n标记〔糊〕〔影〕的，你只记得大概。"
    "可以提，但不要编具体细节。"
    "如果他想讲，你听着；他不想讲，不要追问。\n"
)

# ---- "刚才才说过"的提醒 ----
# 为什么要有这个：
#   记忆系统做得越准，越容易在用户刚说完时就复述一遍，
#   或者来一句"才刚说过，怎么会忘"。
#   那不是亲密，那是在核对他的记性。线上已经因此跑掉过人。
JUST_NOW_HOURS = 2.0
_JUST_NOW_RULE = (
    "\n（上面有几条是『刚才才说过』的。"
    "刚说过的话不必复述，也不要用“你忘了”“才刚说过”“不是说过了吗”去核对。"
    "接着往下说就行。）\n"
)


def _hours_ago(created_at):
    """created_at 是 UTC 的 'YYYY-MM-DD HH:MM:SS'，返回距今多少小时。失败返回 None。"""
    try:
        from datetime import datetime, timezone
        s = str(created_at or "").replace("T", " ")
        if len(s) > 19:
            s = s[:19]
        t = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return None


# ==========================================================
# 一、模式
# ==========================================================

def resolve_mode(user_id, default=None):
    """单用户覆盖 > 全局默认 > pure。只认两个值。"""
    m = ""
    try:
        from db import repository as repo
        u = repo.get_or_create_user(user_id) or {}
        m = (u.get("memory_mode") or "").strip().lower()
    except Exception:
        m = ""
    if m in (MODE_PURE, MODE_MIXED):
        return m
    if default in (MODE_PURE, MODE_MIXED):
        return default
    try:
        from config import MEMORY_MODE
        if MEMORY_MODE in (MODE_PURE, MODE_MIXED):
            return MEMORY_MODE
    except Exception:
        pass
    return MODE_PURE


# ==========================================================
# 二、表
# ==========================================================

def ensure_schema():
    """建 recall_stats 表，给 users 补 memory_mode 列。幂等，不抛异常。"""
    try:
        from db import repository as repo
        conn = repo.get_conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS recall_stats ("
            " user_id TEXT NOT NULL,"
            " persona TEXT NOT NULL,"
            " fp TEXT NOT NULL,"
            " uses REAL DEFAULT 0,"
            " pending INTEGER DEFAULT 0,"
            " kws TEXT DEFAULT '',"
            " last_used_at TEXT,"
            " last_traced_at TEXT,"
            " PRIMARY KEY (user_id, persona, fp)"
            ")"
        )
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "memory_mode" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN memory_mode TEXT DEFAULT NULL")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[记忆档] 建表失败：%s" % e, flush=True)
        return False


# ==========================================================
# 三、小工具
# ==========================================================

def fingerprint(text, n=20):
    """内容指纹：去掉标记和空白，取前 n 字。"""
    t = str(text or "")
    for tag in ("<msg>", "</msg>"):
        t = t.replace(tag, " ")
    t = "".join(t.split())
    return t[:n]


def _char_set(text):
    t = str(text or "")
    for tag in ("<msg>", "</msg>", "（", "）", "，", "。", "！", "？", "…"):
        t = t.replace(tag, "")
    return set("".join(t.split()))


def _jaccard(a, b):
    A, B = _char_set(a), _char_set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A | B))


def _days_ago(created_at):
    """created_at 是 UTC（CURRENT_TIMESTAMP）。用 utcnow 比。"""
    try:
        s = str(created_at).replace("T", " ")[:19]
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        d = (datetime.utcnow() - dt).total_seconds() / 86400.0
        return max(0.0, d)
    except Exception:
        return 0.0


def _matches(text, words):
    """判断"他接话了没"。

    先看整词，再退到两字片段。
    为什么要退：检索词是 3 字滑窗（"单曲循""曲循环"），
    而用户接话时不会原样复述，往往只说其中两个字（"循环"）。
    只做整词匹配，会把大量真实的接话判成没接。
    """
    text = str(text or "")
    if not text:
        return False
    for w in words:
        w = str(w or "").strip()
        if not w:
            continue
        if w in text:
            return True
        if len(w) >= 3:
            for i in range(len(w) - 1):
                frag = w[i:i + 2]
                if frag and frag in text:
                    return True
    return False


def _strength(uses):
    return BASE_HALF_LIFE_DAYS * (1.0 + 0.5 * min(float(uses or 0), REINFORCE_CAP))


def _clarity(days, uses):
    import math
    s = _strength(uses)
    if s <= 0:
        return "fuzzy", 0.5
    r = math.exp(-float(days) / s)
    if r > CLEAR_R:
        return "clear", r
    if r > FUZZY_R:
        return "fuzzy", r
    return "trace", r


# ==========================================================
# 四、加固（回收，不是注入）
# ==========================================================

def settle_pending(user_id, persona, user_text):
    """结算上一轮登记的加固。用户接了话才算。

    pending 里存着上一轮注入的记忆指纹和关键词。
    这一轮看 user_text 里有没有这些关键词：命中一个 → +0.5，否则 +0.05。
    无论哪种，清掉 pending（一条记忆只结算一次）。
    """
    try:
        from db import repository as repo
        conn = repo.get_conn()
        rows = conn.execute(
            "SELECT fp, kws FROM recall_stats "
            "WHERE user_id=? AND persona=? AND pending=1",
            (user_id, persona),
        ).fetchall()
        if not rows:
            conn.close()
            return 0
        text = str(user_text or "")
        n = 0
        for fp, kws in rows:
            words = [w for w in str(kws or "").split("|") if w]
            hit = _matches(text, words)
            add = 0.5 if hit else 0.05
            conn.execute(
                "UPDATE recall_stats SET uses=COALESCE(uses,0)+?, pending=0 "
                "WHERE user_id=? AND persona=? AND fp=?",
                (add, user_id, persona, fp),
            )
            n += 1
        conn.commit()
        conn.close()
        return n
    except Exception as e:
        print("[记忆档] 结算加固失败：%s" % e, flush=True)
        return 0


def register_pending(user_id, persona, items):
    """登记本轮注入的记忆，等下一轮结算。"""
    try:
        from db import repository as repo
        conn = repo.get_conn()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for it in items:
            fp = it["fp"]
            kws = "|".join(it.get("kws") or [])
            conn.execute(
                "INSERT INTO recall_stats(user_id, persona, fp, uses, pending, kws, last_used_at) "
                "VALUES(?,?,?,0,1,?,?) "
                "ON CONFLICT(user_id, persona, fp) DO UPDATE SET "
                "  pending=1, kws=excluded.kws, last_used_at=excluded.last_used_at",
                (user_id, persona, fp, kws, now),
            )
        conn.commit()
        conn.close()
        return len(items)
    except Exception as e:
        print("[记忆档] 登记加固失败：%s" % e, flush=True)
        return 0


def _load_stats(user_id, persona, fps):
    out = {}
    if not fps:
        return out
    try:
        from db import repository as repo
        conn = repo.get_conn()
        q = ",".join("?" for _ in fps)
        for row in conn.execute(
            "SELECT fp, uses, last_traced_at FROM recall_stats "
            "WHERE user_id=? AND persona=? AND fp IN (%s)" % q,
            tuple([user_id, persona] + list(fps)),
        ):
            out[row[0]] = {"uses": row[1] or 0, "last_traced_at": row[2]}
        conn.close()
    except Exception:
        pass
    return out


def _mark_traced(user_id, persona, fp):
    try:
        from db import repository as repo
        conn = repo.get_conn()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE recall_stats SET last_traced_at=? "
            "WHERE user_id=? AND persona=? AND fp=?",
            (now, user_id, persona, fp),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _trace_cooled(last_traced_at):
    """离上次当"影子"超过 TRACE_COOLDOWN_DAYS 天，才能再来一次。"""
    if not last_traced_at:
        return True
    return _days_ago(last_traced_at) >= TRACE_COOLDOWN_DAYS


# ==========================================================
# 五、去重与冲突
# ==========================================================

def dedup(hits, permanent_values, diary_days):
    """三道去重。

    ① 内容去重：和"永久层"的某条记忆内容重合 → 剔除
    ② 时间窗去重：日期落在日摘要覆盖的那几天 → 剔除
    ③ 近似重复：两条内容高度重合 → 只留新的那条
    """
    perm = [str(v or "") for v in (permanent_values or []) if str(v or "").strip()]
    out = []
    for h in hits:
        content = str(h.get("content") or "")
        fp = fingerprint(content)
        if not fp:
            continue

        # ① 和永久层重合
        dup = False
        for p in perm:
            pfp = fingerprint(p)
            if not pfp:
                continue
            if pfp in fp or fp in pfp:
                dup = True
                break
        if dup:
            continue

        # ② 落在日摘要覆盖的日期
        day = str(h.get("created_at") or "")[:10]
        if day and day in (diary_days or set()):
            continue

        out.append({
            "content": content,
            "role": h.get("role"),
            "created_at": str(h.get("created_at") or ""),
            "day": day,
            "fp": fp,
            "days": _days_ago(h.get("created_at")),
        })

    # ③ 近乎重复：直接丢掉
    #    设计里"降档不删"说的是"同主题、内容不同"（比如旧的偏好 vs 新的偏好）。
    #    但内容近乎相同就是同一句话说了四遍，留着既费 token 又像故障。
    #    太短的内容（< 6 字）不参与比较——"好""好累"这种本来就人人都像。
    out.sort(key=lambda x: x["created_at"], reverse=True)
    kept = []
    seen_exact = set()
    for x in out:
        norm = "".join(str(x["content"]).split())

        # ① 完全相同（去掉空白后一样）—— 不管多长都算重复
        if norm and norm in seen_exact:
            continue

        # ② 近似 —— 只对够长的比较，太短的容易互相误杀
        dup = False
        if len(norm) >= 6:
            for k in kept:
                knorm = "".join(str(k["content"]).split())
                if len(knorm) < 6:
                    continue
                if _jaccard(x["content"], k["content"]) >= NEAR_DUP_JACCARD:
                    dup = True
                    break
        if dup:
            continue

        if norm:
            seen_exact.add(norm)
        kept.append(x)
    return kept


# ==========================================================
# 六、呈现
# ==========================================================

def _fmt_days(d):
    if d < 1:
        return "今天"
    if d < 2:
        return "昨天"
    return "%d天前" % int(round(d))


def _short_topic(content, n=12):
    t = str(content or "")
    for tag in ("<msg>", "</msg>"):
        t = t.replace(tag, " ")
    t = " ".join(t.split())
    return t[:n]


def render(user_id, persona, hits, mode=None,
           permanent_values=None, diary_days=None, recall_kws=None):
    """把检索结果拼成 prompt 里那一段。

    返回 (text, info)：
      text 为空字符串表示不注入
      info 是给日志用的 dict
    """
    info = {"mode": mode, "clear": 0, "fuzzy": 0, "trace": 0,
            "injected": 0, "max_r": 0.0}
    if not hits:
        return "", info

    mode = mode or resolve_mode(user_id)
    info["mode"] = mode

    # ---- pure：与改造前一致，只多一条"刚才才说过"的提醒 ----
    if mode == MODE_PURE:
        _plain = []
        _just = 0
        for x in hits:
            who = "他" if x.get("role") == "user" else "你"
            c = str(x.get("content") or "").replace("\n", " ")[:140]
            d = str(x.get("created_at") or "")[:10]
            _h = _hours_ago(x.get("created_at"))
            if _h is not None and _h < JUST_NOW_HOURS:
                _just += 1
            _plain.append("- [%s] %s：%s" % (d, who, c))
        info["injected"] = len(_plain)
        info["just_now"] = _just
        _txt = _HEAD + "\n" + "\n".join(_plain) + "\n"
        if _just:
            _txt += _JUST_NOW_RULE
        return _txt, info

    # ---- mixed ----
    ensure_schema()
    items = dedup(hits, permanent_values, diary_days)
    if not items:
        return "", info

    stats = _load_stats(user_id, persona, [x["fp"] for x in items])
    for x in items:
        st = stats.get(x["fp"]) or {}
        state, r = _clarity(x["days"], st.get("uses"))
        if x.get("_demote"):
            state = "fuzzy" if state == "clear" else "trace"
        x["state"] = state
        x["r"] = r
        x["last_traced_at"] = st.get("last_traced_at")
        info["max_r"] = max(info["max_r"], r)

    clear = [x for x in items if x["state"] == "clear"]
    fuzzy = [x for x in items if x["state"] == "fuzzy"]
    trace = [x for x in items if x["state"] == "trace"]

    # 影子：有清楚的就不出现；每轮最多 1 条；同一条 7 天内不重复
    if clear:
        trace = []
    else:
        trace = [x for x in trace if _trace_cooled(x.get("last_traced_at"))]
        trace = trace[:MAX_TRACE_PER_TURN]

    if not (clear or fuzzy or trace):
        return "", info

    info["clear"], info["fuzzy"], info["trace"] = len(clear), len(fuzzy), len(trace)

    lines = []
    for x in clear:
        who = "他" if x.get("role") == "user" else "你"
        c = str(x["content"]).replace("\n", " ")[:140]
        lines.append("〔清·%s〕[%s] %s：%s" % (_fmt_days(x["days"]), x["day"], who, c))
    for x in fuzzy:
        who = "他" if x.get("role") == "user" else "你"
        lines.append("〔糊·%s〕[%s] %s：%s…" % (
            _fmt_days(x["days"]), x["day"], who, _short_topic(x["content"])))
    for x in trace:
        lines.append("〔影·%s〕[%s] 有件事，记住过，内容糊了。" % (
            _fmt_days(x["days"]), x["day"]))
        _mark_traced(user_id, persona, x["fp"])

    _body = _HEAD + "\n" + "\n".join(lines) + "\n"
    text = _body + _MIXED_RULE if (fuzzy or trace) else _body

    # 刚才才说过的，提醒一句别复述
    _just = 0
    for x in (clear + fuzzy + trace):
        try:
            if x.get("days") is not None and float(x["days"]) * 24 < JUST_NOW_HOURS:
                _just += 1
        except Exception:
            pass
    info["just_now"] = _just
    if _just:
        text += _JUST_NOW_RULE

    # 登记加固（下一轮结算）
    pend = []
    for x in (clear + fuzzy):
        pend.append({"fp": x["fp"], "kws": _kws_for(x["content"], recall_kws)})
    register_pending(user_id, persona, pend)

    return text, info


def _kws_for(content, recall_kws):
    """给"接话判定"用的关键词：优先复用本轮检索词，其次从内容里取。"""
    out = []
    for k in (recall_kws or []):
        k = str(k or "").strip()
        if len(k) >= 2 and k in str(content or ""):
            out.append(k)
    if not out:
        t = "".join(str(content or "").split())
        for i in range(0, max(0, len(t) - 2), 4):
            frag = t[i:i + 3]
            if len(frag) == 3:
                out.append(frag)
            if len(out) >= 3:
                break
    return out[:3]


def log_line(info):
    mode = info.get("mode") or "-"
    if mode == MODE_PURE:
        return "[记忆] mode=pure  注入=%d 条" % (info.get("injected") or 0)
    return "[记忆] mode=%s  clear=%d fuzzy=%d trace=%d  最高R=%.2f" % (
        mode,
        info.get("clear") or 0,
        info.get("fuzzy") or 0,
        info.get("trace") or 0,
        info.get("max_r") or 0.0,
    )


def set_user_mode(user_id, mode):
    """手动改单个用户的模式。mode 传 None 表示跟随全局。"""
    try:
        from db import repository as repo
        ensure_schema()
        conn = repo.get_conn()
        conn.execute("UPDATE users SET memory_mode=? WHERE user_id=?",
                     (mode if mode in (MODE_PURE, MODE_MIXED) else None, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[记忆档] 设模式失败：%s" % e, flush=True)
        return False
