"""陪伴 / 恋爱 模式。

这一层只做一件事：告诉调用方"这个人现在走哪条模式"。

规则
  默认           romance（维持现有行为，零风险）
  白名单用户      companion（目前只有「大肥鱼」）
  数据库 users.mode 字段优先级最高（后面做切换入口时用）

为什么放在 core 而不是 modules：
  它被 chat / stage / render 都要用，属于内核判定；
  真正的恋爱逻辑（好感度推进、表白、吃醋）才应该被抽到 modules/romance。
"""

from __future__ import annotations

import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "love_bot.db")

DEFAULT_MODE = os.getenv("PEINI_MODE", "romance").strip().lower()

# 这些人默认走陪伴模式，不看数据库字段
COMPANION_USERS = {"大肥鱼", "dafeiyu", "da_fei_yu"}

_lock = threading.Lock()
_cache: dict[str, str] = {}


def normalize(mode: str | None) -> str:
    m = (mode or "").strip().lower()
    return m if m in ("companion", "romance") else DEFAULT_MODE


def _query(user_id: str) -> tuple[str, str]:
    """返回 (username, mode字段)。查不到就返回空。"""
    try:
        with _lock:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            try:
                row = conn.execute(
                    "select username, coalesce(mode, '') from users where user_id=?",
                    (user_id,),
                ).fetchone()
            finally:
                conn.close()
        if not row:
            return "", ""
        return (row[0] or ""), (row[1] or "")
    except Exception as e:  # 数据库不在、字段没加，都不应该让聊天挂掉
        print(f"[模式] 读取失败，按默认处理：{e}", flush=True)
        return "", ""


def get_mode(user_id: str) -> str:
    """当前模式：romance / companion。"""
    if not user_id:
        return DEFAULT_MODE

    cached = _cache.get(user_id)
    if cached:
        return cached

    username, db_mode = _query(user_id)

    if username and username in COMPANION_USERS:
        mode = "companion"
    elif db_mode in ("companion", "romance"):
        mode = db_mode
    else:
        mode = DEFAULT_MODE

    _cache[user_id] = mode
    return mode


def is_companion(user_id: str) -> bool:
    return get_mode(user_id) == "companion"


def is_romance(user_id: str) -> bool:
    return get_mode(user_id) == "romance"


def set_mode(user_id: str, mode: str) -> None:
    """切换模式（切换入口以后再加，这里先给内核用）。"""
    m = normalize(mode)
    try:
        with _lock:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            try:
                conn.execute("update users set mode=? where user_id=?", (m, user_id))
                conn.commit()
            finally:
                conn.close()
        _cache[user_id] = m
    except Exception as e:
        print(f"[模式] 写入失败：{e}", flush=True)


def clear_cache() -> None:
    _cache.clear()
