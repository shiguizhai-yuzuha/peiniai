"""DS 页面：仿 DeepSeek 网页端的会话存储与流式对话。

自己用，不做额外审核；模型自身的策略仍在（这里不绕过）。
上下文策略：按字数预算滑动窗口（默认 24k 字），系统提示固定在最前。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

from config import DB_PATH

MAX_CONTEXT_CHARS = 24000


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def ensure_schema():
    c = _conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS ds_convos (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT,
        model TEXT DEFAULT 'deepseek-chat',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ds_msgs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        convo_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        reasoning TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_ds_msgs_convo ON ds_msgs(convo_id, id);
    CREATE INDEX IF NOT EXISTS idx_ds_convos_user ON ds_convos(user_id, updated_at);
    """)
    c.commit()
    c.close()


def list_convos(user_id: str, limit: int = 60):
    c = _conn()
    rows = c.execute(
        "SELECT id, title, model, updated_at FROM ds_convos "
        "WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def create_convo(user_id: str, title: str = "新对话", model: str = "deepseek-chat") -> str:
    cid = uuid.uuid4().hex[:16]
    c = _conn()
    c.execute("INSERT INTO ds_convos(id,user_id,title,model) VALUES(?,?,?,?)",
              (cid, user_id, title, model))
    c.commit()
    c.close()
    return cid


def delete_convo(user_id: str, cid: str):
    c = _conn()
    c.execute("DELETE FROM ds_msgs WHERE convo_id=?", (cid,))
    c.execute("DELETE FROM ds_convos WHERE id=? AND user_id=?", (cid, user_id))
    c.commit()
    c.close()


def rename_convo(user_id: str, cid: str, title: str):
    c = _conn()
    c.execute("UPDATE ds_convos SET title=? WHERE id=? AND user_id=?", (title[:40], cid, user_id))
    c.commit()
    c.close()


def get_msgs(cid: str):
    c = _conn()
    rows = c.execute(
        "SELECT id, role, content, reasoning, created_at FROM ds_msgs WHERE convo_id=? ORDER BY id",
        (cid,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def add_msg(cid: str, role: str, content: str, reasoning: str = ""):
    c = _conn()
    c.execute("INSERT INTO ds_msgs(convo_id,role,content,reasoning) VALUES(?,?,?,?)",
              (cid, role, content, reasoning or ""))
    c.execute("UPDATE ds_convos SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
    c.commit()
    c.close()


def touch_convo(user_id: str, cid: str, model: str, title: str | None = None):
    c = _conn()
    if title:
        c.execute("UPDATE ds_convos SET model=?, title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                  (model, title[:40], cid))
    else:
        c.execute("UPDATE ds_convos SET model=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                  (model, cid))
    c.commit()
    c.close()


def build_context(cid: str, system: str = "", budget: int = MAX_CONTEXT_CHARS):
    """滑动窗口：从最近往前取，超预算就截断。系统提示固定在最前。"""
    history = get_msgs(cid)
    picked = []
    used = 0
    for m in reversed(history):
        text = m.get("content") or ""
        if not text:
            continue
        if used + len(text) > budget and picked:
            break
        picked.append({"role": m["role"], "content": text})
        used += len(text)
    picked.reverse()
    out = []
    if system:
        out.append({"role": "system", "content": system})
    out.extend(picked)
    return out

# ---------- 余额 ----------

def balance_of(user_id: str) -> float:
    try:
        c = _conn()
        row = c.execute("SELECT COALESCE(balance,0) FROM users WHERE user_id=?", (user_id,)).fetchone()
        c.close()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0


def spend(user_id: str, amount: float) -> float:
    """扣钱，返回扣完的余额。"""
    try:
        c = _conn()
        c.execute("UPDATE users SET balance = COALESCE(balance,0) - ? WHERE user_id=?",
                  (abs(amount), user_id))
        c.commit()
        row = c.execute("SELECT COALESCE(balance,0) FROM users WHERE user_id=?", (user_id,)).fetchone()
        c.close()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0


# ---------- 上下文档位 ----------

TIERS = {
    "short": {"chars": 8000, "label": "短 · 8k 字"},
    "mid": {"chars": 24000, "label": "中 · 24k 字"},
    "long": {"chars": 48000, "label": "长 · 48k 字"},
    "max": {"chars": 96000, "label": "超长 · 96k 字"},
}


def tier_chars(tier: str) -> int:
    return TIERS.get(tier or "mid", TIERS["mid"])["chars"]


# ---------- 文件 ----------

def add_file(convo_id: str, name: str, text: str) -> int:
    c = _conn()
    c.execute("CREATE TABLE IF NOT EXISTS ds_files("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, convo_id TEXT, name TEXT, "
              "content TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    c.execute("INSERT INTO ds_files(convo_id,name,content) VALUES(?,?,?)", (convo_id, name, text))
    fid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.commit()
    c.close()
    return int(fid)


def list_files(convo_id: str):
    try:
        c = _conn()
        rows = c.execute("SELECT id, name, LENGTH(content) n FROM ds_files WHERE convo_id=? ORDER BY id",
                         (convo_id,)).fetchall()
        c.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def file_texts(convo_id: str, limit: int = 3, each: int = 12000):
    try:
        c = _conn()
        rows = c.execute("SELECT name, content FROM ds_files WHERE convo_id=? ORDER BY id DESC LIMIT ?",
                         (convo_id, limit)).fetchall()
        c.close()
        return [(r["name"], (r["content"] or "")[:each]) for r in rows]
    except Exception:
        return []
