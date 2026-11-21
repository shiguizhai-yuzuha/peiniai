"""陪伴 / 恋爱 模式（按角色区分）。

规则（优先级从高到低）
  ①  有人手动切过       user_modes 表里那一行说了算
  ②  角色默认           COMPANION_PERSONAS 里的角色默认陪伴，其余默认恋爱
  ③  账号白名单         （兼容旧逻辑，按 username / nickname）
  ④  全局默认           DEFAULT_MODE（romance）

为什么按角色：
  「大肥鱼」是角色，不是账号。同一个账号换个角色，关系不一样是正常的。
"""

from __future__ import annotations

import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "love_bot.db")

DEFAULT_MODE = os.getenv("PEINI_MODE", "romance").strip().lower()

# 这些角色默认走「陪伴」：不谈关系，只陪着
COMPANION_PERSONAS = {"大肥鱼", "dafeiyu", "da_fei_yu"}

# 兼容：这些账号名/昵称默认走陪伴（旧的白名单）
COMPANION_USERS = {"大肥鱼", "dafeiyu", "da_fei_yu"}

_lock = threading.Lock()
_cache: dict[tuple[str, str], str] = {}
_ready = False


def normalize(mode: str | None) -> str:
    m = (mode or "").strip().lower()
    return m if m in ("companion", "romance") else DEFAULT_MODE


def _ensure_table(conn) -> None:
    global _ready
    if _ready:
        return
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_modes ("
        " user_id TEXT NOT NULL,"
        " persona TEXT NOT NULL,"
        " mode TEXT NOT NULL,"
        " updated_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (user_id, persona))"
    )
    conn.commit()
    _ready = True


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    _ensure_table(conn)
    return conn


def _query_user(user_id: str) -> tuple[str, str]:
    try:
        with _lock:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            try:
                row = conn.execute(
                    "select coalesce(username,''), coalesce(nickname,'') from users where user_id=?",
                    (user_id,),
                ).fetchone()
            finally:
                conn.close()
        if not row:
            return "", ""
        return row[0], row[1]
    except Exception as e:
        print(f"[模式] 读用户失败，按默认处理：{e}", flush=True)
        return "", ""


def _query_override(user_id: str, persona: str) -> str:
    try:
        with _lock:
            conn = _conn()
            try:
                row = conn.execute(
                    "select mode from user_modes where user_id=? and persona=?",
                    (user_id, persona or ""),
                ).fetchone()
                if not row:
                    row = conn.execute(
                        "select mode from user_modes where user_id=? and persona='*'",
                        (user_id,),
                    ).fetchone()
            finally:
                conn.close()
        if row and row[0] in ("companion", "romance"):
            return row[0]
    except Exception as e:
        print(f"[模式] 读覆盖失败，按默认处理：{e}", flush=True)
    return ""


def get_mode(user_id: str, persona: str = "") -> str:
    """当前模式：romance / companion。"""
    key = (user_id or "", persona or "")
    if key in _cache:
        return _cache[key]

    mode = ""

    # ① 手动切过
    if user_id:
        mode = _query_override(user_id, persona)

    # ② 角色默认
    if not mode and persona and persona in COMPANION_PERSONAS:
        mode = "companion"

    # ③ 账号白名单（兼容旧逻辑）
    if not mode and user_id:
        username, nickname = _query_user(user_id)
        if (username and username in COMPANION_USERS) or (nickname and nickname in COMPANION_USERS):
            mode = "companion"

    # ④ 全局默认
    if not mode:
        mode = DEFAULT_MODE

    _cache[key] = mode
    return mode


def is_companion(user_id: str, persona: str = "") -> bool:
    return get_mode(user_id, persona) == "companion"


def is_romance(user_id: str, persona: str = "") -> bool:
    return get_mode(user_id, persona) == "romance"


def set_mode(user_id: str, mode: str, persona: str = "") -> None:
    """记下这一次切换（persona 传空表示对这个人全部角色生效）。"""
    m = normalize(mode)
    try:
        with _lock:
            conn = _conn()
            try:
                conn.execute(
                    "insert into user_modes(user_id, persona, mode, updated_at) "
                    "values(?,?,?,CURRENT_TIMESTAMP) "
                    "on conflict(user_id, persona) do update set mode=excluded.mode, "
                    "updated_at=CURRENT_TIMESTAMP",
                    (user_id, persona or "", m),
                )
                conn.commit()
            finally:
                conn.close()
        for k in [k for k in _cache if k[0] == (user_id or "")]:
            _cache.pop(k, None)
    except Exception as e:
        print(f"[模式] 写入失败：{e}", flush=True)


def clear_cache() -> None:
    _cache.clear()
