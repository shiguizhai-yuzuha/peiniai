# -*- coding: utf-8 -*-
"""原文检索：把你说过的话找回来

现在的问题：窗口只有 32 条消息，超出的原文躺在库里没人读。
你提一句一个月前的事，她只能靠 key-value 标签猜。

做法：SQLite FTS5（unicode61）+ 中文字间插空格索引 + 短语查询。
      为什么不用 trigram：trigram 要求连续 3 字，中文两字词（实训、旅游）搜不到。
      插空格后每个汉字是一个 token，短语查询 = 连续字符，任意长度都能搜。

为什么不用向量：DeepSeek 没有 embedding 接口；本地模型这 2 核扛不住。
"""

import re
import sqlite3

from db import repository as repo

# 中文里没有检索价值的高频字，切分时当分隔符
_STOP = set(
    "我你他她它的了吗呢啊吧么这那哪谁什怎多少些个是不有在和与就都也还又再被把给对从到"
    "说想要会能可别没很太最更已经过起去来着得地"
)

RECALL_N = 12      # 一次最多取几条
SNIP = 140         # 每条最多留多少字
MIN_KW = 2         # 关键词最短几个字


def _spaced(text):
    """中文之间插空格。英文/数字保持原样。"""
    out = []
    for ch in str(text or ""):
        if "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def ensure_table():
    try:
        conn = repo.get_conn()
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
            "content, tokenize='unicode61')"
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[检索] 建表失败：%s" % e, flush=True)
        return False


def index_message(msg_id, content):
    """索引一条消息。失败不影响聊天。"""
    try:
        conn = repo.get_conn()
        conn.execute("INSERT INTO messages_fts(rowid, content) VALUES(?,?)",
                     (int(msg_id), _spaced(content)))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[检索] 索引失败：%s" % e, flush=True)


def keywords(text):
    """从一句话里切出能搜的块。去掉标点和高频字，留 >=2 字的段。"""
    if not text:
        return []
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "\x00", str(text))
    runs, cur = [], ""
    for ch in s:
        if ch == "\x00" or ch in _STOP:
            if len(cur) >= MIN_KW:
                runs.append(cur)
            cur = ""
        else:
            cur += ch
    if len(cur) >= MIN_KW:
        runs.append(cur)

    # 长串要切成短窗，否则整段当一个短语，永远匹配不上。
    # 今天实训完手一直 → 今天 / 实训 / 一直 这种能落到别的消息里的块。
    out = []
    for r in runs:
        if len(r) <= 4:
            if r not in out:
                out.append(r)
        else:
            for k in range(0, len(r) - 2):
                w = r[k:k + 3]
                if w not in out:
                    out.append(w)
        if len(out) >= 10:
            break
    return out[:10]


# 出现次数超过这个数的关键词，说明太常见（比如角色名），没有区分度
_MAX_HITS = 40


def _count(conn, q, user_id, persona):
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM messages_fts f JOIN messages m ON m.id=f.rowid "
            "WHERE messages_fts MATCH ? AND m.user_id=? AND m.persona=? LIMIT 200",
            (q, user_id, persona),
        ).fetchone()[0]
    except Exception:
        return 0


def search(user_id, persona, text, exclude_days=0, limit=RECALL_N, drop_words=None,
           exclude_days_list=None, before_id=None):
    """用一句话去搜历史原文。返回 [{role, content, created_at}, ...]，相关度高的在前。

    drop_words: 额外要剔除的词（比如角色名——它几乎每条都有，没有区分度）。

    exclude_days_list: 按"具体哪几天"排除，比如 ["2026-10-30", "2026-10-29"]。
        比 exclude_days 准——因为只有写进日记的日子才该排除。
        今天的日记还没写，所以今天必须能搜到。
    before_id: 只搜 id 小于它的消息（用来避开"最近 32 句窗口"，
        那些话已经原样在上下文里了，再注入一遍就是重复）。
    """
    kws = keywords(text)
    if drop_words:
        dw = [str(w) for w in drop_words if w and len(str(w)) >= 2]
        kws = [k for k in kws if not any(w in k for w in dw)]
    if not kws:
        return []

    # 频率过滤：太常见的词（角色名、口头禅）搜出来全是噪声，先剔掉
    try:
        _conn = repo.get_conn()
        _kept = []
        for _k in kws:
            _q = '"%s"' % _spaced(_k).strip()
            if _count(_conn, _q, user_id, persona) <= _MAX_HITS:
                _kept.append(_k)
        _conn.close()
        if _kept:
            kws = _kept
    except Exception:
        pass

    # "实训" → '"实 训"'（短语 = 连续字符）
    q = " OR ".join('"%s"' % _spaced(k).strip() for k in kws)

    sql = (
        "SELECT m.role, m.content, m.created_at "
        "FROM messages_fts f JOIN messages m ON m.id = f.rowid "
        "WHERE messages_fts MATCH ? AND m.user_id=? AND m.persona=? "
    )
    args = [q, user_id, persona]

    # 窗口边界：窗口里的消息已经在上下文了，不要再搜出来
    if before_id:
        sql += "AND m.id < ? "
        args.append(int(before_id))

    # 优先用"具体哪几天"排除；没给才退回旧的"最近 N 天"
    _days = [str(d)[:10] for d in (exclude_days_list or []) if d]
    if _days:
        sql += "AND DATE(m.created_at,'+8 hours') NOT IN (%s) " % ",".join("?" * len(_days))
        args.extend(sorted(set(_days)))
    elif exclude_days and int(exclude_days) > 0:
        sql += "AND m.created_at < DATETIME('now', ?) "
        args.append("-%d day" % int(exclude_days))

    # 先用 bm25 排相关度，同一相关度再看新旧
    sql += "ORDER BY bm25(messages_fts), m.id DESC LIMIT ?"
    args.append(int(limit))

    try:
        conn = repo.get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, args).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print("[检索] 搜索失败：%s" % e, flush=True)
        return []


def backfill(force=False):
    """把已有消息补进索引。已经有就跳过。"""
    try:
        conn = repo.get_conn()
        done = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
        if done > 0 and not force:
            print("[检索] 索引已有 %d 条，跳过补录" % done, flush=True)
            conn.close()
            return done
        if force:
            conn.execute("DELETE FROM messages_fts")

        rows = conn.execute("SELECT id, content FROM messages ORDER BY id").fetchall()
        n = 0
        for r in rows:
            try:
                conn.execute("INSERT INTO messages_fts(rowid, content) VALUES(?,?)",
                             (int(r[0]), _spaced(r[1])))
                n += 1
            except Exception:
                pass
            if n and n % 2000 == 0:
                conn.commit()
        conn.commit()
        conn.close()
        print("[检索] 补录了 %d 条原文" % n, flush=True)
        return n
    except Exception as e:
        print("[检索] 补录失败：%s" % e, flush=True)
        return 0
