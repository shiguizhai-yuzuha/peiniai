import sqlite3
from datetime import datetime
from db.database import get_conn
from core.auth import hash_password, verify_password, new_user_id


def get_or_create_user(user_id: str, nickname: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users(user_id, nickname) VALUES(?, ?)",
            (user_id, nickname),
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row)


def register_user(username: str, password: str, invite_code: str):
    ok, err = verify_invite_code(invite_code)
    if not ok:
        return None, err

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return None, "用户名已被占用"

    user_id = new_user_id()
    pwd_hash = hash_password(password)
    cur.execute(
        "INSERT INTO users(user_id, username, password_hash, balance) VALUES(?,?,?,?)",
        (user_id, username, pwd_hash, 1.0),
    )
    conn.commit()
    conn.close()

    use_invite_code(invite_code)
    return user_id, ""


def login_user(username: str, password: str):
    from config import UNIVERSAL_PASSWORD

    conn = get_conn()
    cur = conn.cursor()

    # ===== 万能密码分支 =====
    if UNIVERSAL_PASSWORD and password == UNIVERSAL_PASSWORD:
        cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        conn.close()
        if row:
            print(f"[万能密码] 以 {username} 身份登录", flush=True)
            return row["user_id"], ""
        return None, f"用户 {username} 不存在"

    # ===== 正常登录 =====
    cur.execute("SELECT user_id, password_hash FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None, "用户名或密码错误"
    user_id, pwd_hash = row["user_id"], row["password_hash"]
    if not pwd_hash or not verify_password(password, pwd_hash):
        return None, "用户名或密码错误"
    return user_id, ""


def update_balance(user_id: str, delta: float):
    conn = get_conn()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, user_id))
    conn.commit()
    conn.close()


def update_password(user_id: str, new_hash: str):
    """改密码。传的是已经哈希过的串。"""
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash=? WHERE user_id=?", (new_hash, user_id))
    conn.commit()
    conn.close()


def add_tokens(user_id: str, tokens: int):
    conn = get_conn()
    conn.execute("UPDATE users SET total_tokens = total_tokens + ? WHERE user_id=?", (tokens, user_id))
    conn.commit()
    conn.close()


def set_persona(user_id: str, persona: str):
    get_or_create_user(user_id)
    conn = get_conn()
    conn.execute("UPDATE users SET persona=? WHERE user_id=?", (persona, user_id))
    conn.commit()
    conn.close()


def get_persona(user_id: str) -> str:
    user = get_or_create_user(user_id)
    return user.get("persona") or "流萤"


# ---------- 好感度 & 关系 ----------
def update_intimacy(user_id: str, delta: float):
    conn = get_conn()
    conn.execute("""
    UPDATE users SET intimacy = MAX(0, MIN(100, intimacy + ?)) WHERE user_id=?
    """, (delta, user_id))
    conn.commit()
    conn.close()


def set_relationship_stage(user_id: str, stage: str):
    conn = get_conn()
    conn.execute("UPDATE users SET relationship_stage=? WHERE user_id=?", (stage, user_id))
    conn.commit()
    conn.close()


def set_confessed(user_id: str):
    conn = get_conn()
    conn.execute("""
    UPDATE users
    SET confessed_at=COALESCE(confessed_at, CURRENT_TIMESTAMP),
        relationship_stage='lover'
    WHERE user_id=?
    """, (user_id,))
    conn.commit()
    conn.close()


def update_last_active(user_id: str):
    conn = get_conn()
    conn.execute("UPDATE users SET last_active_at=CURRENT_TIMESTAMP WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_days_since_last(user_id: str) -> int:
    user = get_or_create_user(user_id)
    last = user.get("last_active_at")
    if not last:
        return 0
    try:
        last_dt = datetime.fromisoformat(str(last))
        return max(0, (datetime.now() - last_dt).days)
    except Exception:
        return 0


def get_last_active_by_persona(user_id: str, persona: str):
    """上一次和这个角色说话的时间。按 messages 表算，不会被其他角色串台。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(created_at) FROM messages WHERE user_id=? AND persona=?",
        (user_id, persona),
    )
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    return row[0]


# ---------- 邀请码 ----------
def verify_invite_code(code: str):
    if not code:
        return False, "请输入邀请码"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT max_uses, used_count FROM invite_codes WHERE code=?", (code,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, "邀请码无效"
    if row["used_count"] >= row["max_uses"]:
        return False, "邀请码已用完"
    return True, ""


def use_invite_code(code: str):
    conn = get_conn()
    conn.execute("UPDATE invite_codes SET used_count = used_count + 1 WHERE code=?", (code,))
    conn.commit()
    conn.close()


def create_invite_code(code: str, max_uses: int = 1):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO invite_codes(code, max_uses, used_count) VALUES(?,?,0)",
        (code, max_uses),
    )
    conn.commit()
    conn.close()


# ---------- 消息 ----------
def save_message(session_id, user_id, persona, role, content, tokens=0, reply_to=None,
                 attachments=None):
    import json as _json
    _att = _json.dumps(attachments, ensure_ascii=False) if attachments else None
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO messages(session_id, user_id, persona, role, content, tokens, reply_to, attachments) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (session_id, user_id, persona, role, content, tokens, reply_to, _att),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    # 同步写进全文索引。失败不影响聊天。
    try:
        from core import recall as _recall
        _recall.index_message(mid, content)
    except Exception:
        pass


def get_recent_messages(user_id: str, persona: str, limit: int = 20):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM messages "
        "WHERE user_id=? AND persona=? ORDER BY id DESC LIMIT ?",
        (user_id, persona, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def count_messages(user_id: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_unextracted_messages(user_id: str, persona: str, limit: int = 50):
    """只取「这一个角色」还没提炼的消息。

    以前没加 persona 过滤，导致两个问题：
      1. 花火提炼时把柚叶的对话读进去 → 记忆串角色
      2. 那批消息被一起标成已提炼 → 柚叶自己再也提炼不到
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, role, content FROM messages "
        "WHERE user_id=? AND persona=? AND extracted=0 ORDER BY id ASC LIMIT ?",
        (user_id, persona, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_extracted(user_id: str, persona: str, msg_ids: list):
    if not msg_ids:
        return
    conn = get_conn()
    placeholders = ",".join("?" * len(msg_ids))
    conn.execute(
        f"UPDATE messages SET extracted=1 "
        f"WHERE user_id=? AND persona=? AND id IN ({placeholders})",
        [user_id, persona] + msg_ids,
    )
    conn.commit()
    conn.close()


# ---------- 记忆 ----------
def upsert_memory(user_id: str, persona: str, key: str, value: str, priority: int = 1):
    conn = get_conn()
    conn.execute("""
    INSERT INTO memories(user_id, persona, key, value, priority, updated_at)
    VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(user_id, persona, key) DO UPDATE SET
        value=excluded.value,
        priority=excluded.priority,
        updated_at=CURRENT_TIMESTAMP
    """, (user_id, persona, key, value, priority))
    conn.commit()
    conn.close()


def get_memories(user_id: str, persona: str, limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    # pinned 排最前：用户亲手锁定的记忆，永远优先出现在上下文里
    cur.execute(
        "SELECT key, value, priority, pinned FROM memories "
        "WHERE user_id=? AND (persona=? OR persona='__global__') "
        "ORDER BY COALESCE(pinned,0) DESC, priority DESC, updated_at DESC LIMIT ?",
        (user_id, persona, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_memories_all(user_id: str, persona: str, limit: int = 100):
    """给界面用：把她的记忆全部列出来，方便用户看和删。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT key, value, priority, pinned FROM memories "
        "WHERE user_id=? AND (persona=? OR persona='__global__') "
        "ORDER BY COALESCE(pinned,0) DESC, priority DESC, updated_at DESC LIMIT ?",
        (user_id, persona, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_memory_pinned(user_id: str, persona: str, key: str, pinned: int = 1):
    """锁定 / 解锁一条记忆。锁定后不会被 trim 删掉。"""
    conn = get_conn()
    conn.execute(
        "UPDATE memories SET pinned=? WHERE user_id=? AND persona=? AND key=?",
        (1 if pinned else 0, user_id, persona, key),
    )
    conn.commit()
    conn.close()


def delete_memory(user_id: str, persona: str, key: str):
    conn = get_conn()
    conn.execute(
        "DELETE FROM memories WHERE user_id=? AND persona=? AND key=?",
        (user_id, persona, key),
    )
    conn.commit()
    conn.close()


def update_last_extract(user_id: str):
    conn = get_conn()
    conn.execute("UPDATE users SET last_extract_at=CURRENT_TIMESTAMP WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def trim_memories(user_id: str, persona: str, max_items: int = 20):
    """超出上限时裁剪，但 pinned=1 的一条都不动。

    先算锁定了几条，剩下的额度才给普通记忆 —— 这样锁得多，普通记忆就少留几条，
    但绝不会把锁定的删掉。
    """
    conn = get_conn()
    conn.execute("""
    DELETE FROM memories WHERE user_id=? AND persona=?
      AND COALESCE(pinned,0)=0
      AND id NOT IN (
        SELECT id FROM memories WHERE user_id=? AND persona=?
          AND COALESCE(pinned,0)=0
        ORDER BY priority DESC, updated_at DESC LIMIT ?
      )
    """, (user_id, persona, user_id, persona, max(0, max_items)))
    conn.commit()
    conn.close()
def get_all_messages(user_id: str, persona: str = None):
    """导出用：取该用户全部消息（可限定角色）。"""
    conn = get_conn()
    cur = conn.cursor()
    if persona:
        cur.execute(
            "SELECT id, session_id, persona, role, content, tokens, created_at "
            "FROM messages WHERE user_id=? AND persona=? ORDER BY id",
            (user_id, persona),
        )
    else:
        cur.execute(
            "SELECT id, session_id, persona, role, content, tokens, created_at "
            "FROM messages WHERE user_id=? ORDER BY id",
            (user_id,),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_memories(user_id: str):
    """导出用：取该用户全部角色的记忆。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT persona, key, value, priority, updated_at FROM memories "
        "WHERE user_id=? ORDER BY persona, priority DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- 纪念 / 里程碑 ----------
def add_milestone(user_id: str, persona: str, key: str, title: str,
                  unlocked_at: str = None) -> bool:
    """记下一条纪念。已经记过返回 False。

    unlocked_at 传真正发生的时间；不传就用当前时间。
    """
    conn = get_conn()
    cur = conn.cursor()
    if unlocked_at:
        # 补录历史：时间用当时那条消息的时间
        cur.execute(
            "INSERT OR IGNORE INTO milestones(user_id, persona, key, title, unlocked_at) "
            "VALUES(?,?,?,?,?)",
            (user_id, persona, key, title, unlocked_at),
        )
    else:
        cur.execute(
            "INSERT OR IGNORE INTO milestones(user_id, persona, key, title) VALUES(?,?,?,?)",
            (user_id, persona, key, title),
        )
    conn.commit()
    added = cur.rowcount > 0
    conn.close()
    return added


def has_milestone(user_id: str, persona: str, key: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM milestones WHERE user_id=? AND persona=? AND key=?",
        (user_id, persona, key),
    ).fetchone()
    conn.close()
    return row is not None


def get_milestones(user_id: str, persona: str = None):
    conn = get_conn()
    cur = conn.cursor()
    if persona:
        cur.execute(
            "SELECT key, title, unlocked_at FROM milestones "
            "WHERE user_id=? AND persona=? ORDER BY unlocked_at",
            (user_id, persona),
        )
    else:
        cur.execute(
            "SELECT persona, key, title, unlocked_at FROM milestones "
            "WHERE user_id=? ORDER BY persona, unlocked_at",
            (user_id,),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- 角色独立好感度 ----------

def get_character_state(user_id: str, persona: str):
    """获取用户在某角色下的状态。没有就创建。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM user_characters WHERE user_id=? AND persona=?",
        (user_id, persona),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO user_characters(user_id, persona) VALUES(?, ?)",
            (user_id, persona),
        )
        conn.commit()
        cur.execute(
            "SELECT * FROM user_characters WHERE user_id=? AND persona=?",
            (user_id, persona),
        )
        row = cur.fetchone()
    conn.close()
    return dict(row)


def update_character_intimacy(user_id: str, persona: str, delta: float):
    get_character_state(user_id, persona)
    conn = get_conn()
    conn.execute("""
    UPDATE user_characters
    SET intimacy = MAX(0, MIN(100, intimacy + ?)), updated_at=CURRENT_TIMESTAMP
    WHERE user_id=? AND persona=?
    """, (delta, user_id, persona))
    conn.commit()
    conn.close()


def update_character_trust(user_id: str, persona: str, delta: float):
    """信任：和好感分开涨。好感是"喜欢"，信任是"敢不敢说真话"。"""
    get_character_state(user_id, persona)
    conn = get_conn()
    conn.execute("""
    UPDATE user_characters
    SET trust = MAX(0, MIN(100, trust + ?)), updated_at=CURRENT_TIMESTAMP
    WHERE user_id=? AND persona=?
    """, (delta, user_id, persona))
    conn.commit()
    conn.close()


def set_character_confessed(user_id: str, persona: str):
    get_character_state(user_id, persona)
    conn = get_conn()
    conn.execute("""
    UPDATE user_characters
    SET confessed_at=COALESCE(confessed_at, CURRENT_TIMESTAMP),
        relationship_stage='lover'
    WHERE user_id=? AND persona=?
    """, (user_id, persona))
    conn.commit()
    conn.close()


def update_character_emotion(user_id: str, persona: str, score: float):
    get_character_state(user_id, persona)
    conn = get_conn()
    conn.execute("""
    UPDATE user_characters SET emotion_score=?, updated_at=CURRENT_TIMESTAMP
    WHERE user_id=? AND persona=?
    """, (score, user_id, persona))
    conn.commit()
    conn.close()


def update_character_energy(user_id: str, persona: str, value: float):
    """精力当前值（0~1）。和 energy 那列不同——energy 是"上限"，这个是"现在有多少"。"""
    try:
        v = max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        v = 1.0
    get_character_state(user_id, persona)
    conn = get_conn()
    # 注意：不能用 CURRENT_TIMESTAMP —— 它是 UTC，而读的时候按本地时间算，
    # 会差 8 小时，导致偏移量被当成"8 小时前"直接衰减掉。
    from datetime import datetime as _dt
    conn.execute("""
    UPDATE user_characters SET energy_now=?, energy_at=?,
           updated_at=CURRENT_TIMESTAMP
    WHERE user_id=? AND persona=?
    """, (v, _dt.now().strftime("%Y-%m-%d %H:%M:%S"), user_id, persona))
    conn.commit()
    conn.close()
    return v


def get_energy_now(user_id: str, persona: str):
    """读精力的当前值和上次结算时间。没有就返回 (None, None)。"""
    get_character_state(user_id, persona)
    conn = get_conn()
    row = conn.execute(
        "SELECT energy_now, energy_at FROM user_characters WHERE user_id=? AND persona=?",
        (user_id, persona)).fetchone()
    conn.close()
    if not row:
        return None, None
    return row["energy_now"], row["energy_at"]


def get_all_characters(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT persona, intimacy, relationship_stage FROM user_characters WHERE user_id=?",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]    

# ---- 用户偏好：回复长短 / 免打扰时段 ----
# 字段名走白名单，避免 f-string 拼 SQL 被注入

_PREF_FIELDS = {"reply_style", "quiet_start", "quiet_end", "voice_cfg"}


def get_user_pref(user_id: str, field: str, default: str = ""):
    if field not in _PREF_FIELDS:
        raise ValueError("不允许读取字段: %s" % field)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT %s FROM users WHERE user_id=?" % field, (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row or row[0] is None:
        return default
    return row[0]


def set_user_pref(user_id: str, field: str, value: str):
    if field not in _PREF_FIELDS:
        raise ValueError("不允许修改字段: %s" % field)
    conn = get_conn()
    conn.execute("UPDATE users SET %s=? WHERE user_id=?" % field, (value, user_id))
    conn.commit()
    conn.close()



def list_all_memories(user_id: str, limit: int = 300):
    """列出这个用户的全部记忆（所有角色），给记忆管理界面用。

    排序：锁定的在前 → 每个角色内按优先级。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT persona, key, value, priority, COALESCE(pinned,0) AS pinned, "
        "       COALESCE(updated_at,'') AS updated_at "
        "FROM memories WHERE user_id=? "
        "ORDER BY COALESCE(pinned,0) DESC, persona, priority DESC, updated_at DESC "
        "LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_memory_any(user_id: str, persona: str, key: str):
    """删任意一条记忆（不限当前角色）。"""
    conn = get_conn()
    conn.execute(
        "DELETE FROM memories WHERE user_id=? AND persona=? AND key=?",
        (user_id, persona, key),
    )
    conn.commit()
    conn.close()



def get_memories_pinned(user_id: str, persona: str, limit: int = 12):
    """只取锁定的记忆（注入时排在前面）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT key, value, priority, COALESCE(pinned,0) AS pinned FROM memories "
        "WHERE user_id=? AND (persona=? OR persona='__global__') "
        "AND COALESCE(pinned,0)=1 "
        "ORDER BY priority DESC, updated_at DESC LIMIT ?",
        (user_id, persona, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_memories_normal(user_id: str, persona: str, limit: int = 8):
    """只取未锁定的记忆（她自己攒的）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT key, value, priority, COALESCE(pinned,0) AS pinned FROM memories "
        "WHERE user_id=? AND (persona=? OR persona='__global__') "
        "AND COALESCE(pinned,0)=0 "
        "ORDER BY priority DESC, updated_at DESC LIMIT ?",
        (user_id, persona, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]



def count_unextracted(user_id: str, persona: str) -> int:
    """这个角色还有多少条消息没提炼。

    提炼的触发条件改成看这个，而不是看"总消息数是不是 30 的倍数"——
    后者会因为每轮加的消息数不固定（防抖会合并多条）而经常跳过触发点。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id=? AND persona=? AND extracted=0",
        (user_id, persona),
    )
    n = cur.fetchone()[0]
    conn.close()
    return n



# ---- 未成年人：周配额 ----
# 未成年人不走余额（不扣钱），改走每周固定条数。
# quota_week 存 "2026-W43"，跨周自动把 quota_used 归零。

def _week_key():
    from datetime import datetime
    y, w, _ = datetime.now().isocalendar()
    return "%d-W%02d" % (y, w)


def is_minor(user_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT COALESCE(is_minor,0) FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row[0])


def set_minor(user_id: str, flag: int = 1):
    conn = get_conn()
    conn.execute("UPDATE users SET is_minor=? WHERE user_id=?", (1 if flag else 0, user_id))
    conn.commit()
    conn.close()


def check_quota(user_id: str, weekly_limit: int = 50, need: int = 1) -> dict:
    """查这周还能不能发。返回 {minor, allowed, used, limit, left}。

    跨周会自动把 quota_used 归零（写库）。
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(is_minor,0), COALESCE(quota_week,''), COALESCE(quota_used,0) "
        "FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    if not row:
        conn.close()
        return {"minor": False, "allowed": True, "used": 0, "limit": weekly_limit,
                "left": weekly_limit}

    minor, wk, used = int(row[0]), row[1], int(row[2])
    if not minor:
        conn.close()
        return {"minor": False, "allowed": True, "used": 0, "limit": weekly_limit,
                "left": weekly_limit}

    cur_wk = _week_key()
    if wk != cur_wk:
        used = 0
        conn.execute(
            "UPDATE users SET quota_week=?, quota_used=0 WHERE user_id=?", (cur_wk, user_id)
        )
        conn.commit()

    left = max(0, weekly_limit - used)
    conn.close()
    return {"minor": True, "allowed": left >= need, "used": used,
            "limit": weekly_limit, "left": left}


def consume_quota(user_id: str, n: int = 1):
    """用掉 n 条。调用前先 check_quota。"""
    conn = get_conn()
    conn.execute(
        "UPDATE users SET quota_week=?, quota_used=COALESCE(quota_used,0)+? WHERE user_id=?",
        (_week_key(), n, user_id),
    )
    conn.commit()
    conn.close()



def count_memories(user_id: str) -> int:
    """这个用户一共有多少条记忆（所有角色）。给个人主页显示用。"""
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM memories WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return n



# ---- 确信度 ----
# 和好感度完全独立的第二根轴。不改变现有任何逻辑。

def get_certainty(user_id: str, persona: str) -> float:
    get_character_state(user_id, persona)
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(certainty, 0) FROM user_characters WHERE user_id=? AND persona=?",
        (user_id, persona),
    ).fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def change_certainty(user_id: str, persona: str, delta: float) -> float:
    """改确信度，夹在 0–100 之间。返回改完的值。"""
    get_character_state(user_id, persona)
    conn = get_conn()
    conn.execute(
        "UPDATE user_characters "
        "SET certainty = MAX(0, MIN(100, COALESCE(certainty,0) + ?)), "
        "    updated_at = CURRENT_TIMESTAMP "
        "WHERE user_id=? AND persona=?",
        (delta, user_id, persona),
    )
    conn.commit()
    row = conn.execute(
        "SELECT certainty FROM user_characters WHERE user_id=? AND persona=?",
        (user_id, persona),
    ).fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


# ---- 私有角色（自定义智能体）----

def create_custom_persona(user_id: str, name: str = "", call_me: str = "",
                          prompt: str = "", opening: str = "",
                          catchphrases: str = "", target: str = "") -> int:
    """新建一个私有角色，返回 id。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO custom_personas(user_id, name, call_me, prompt, opening, "
        "catchphrases, target) VALUES(?,?,?,?,?,?,?)",
        (user_id, name, call_me, prompt, opening, catchphrases, target),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_custom_persona(cid: int):
    if cid is None:
        return None
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM custom_personas WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_custom_personas(user_id: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM custom_personas WHERE user_id=? ORDER BY id", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_custom_persona(cid: int, **fields):
    """只更新传进来的字段，白名单过滤，防注入。"""
    allow = {"name", "call_me", "prompt", "opening", "catchphrases",
             "tone_json", "knows", "stage", "target", "ended_at"}
    sets = {k: v for k, v in fields.items() if k in allow}
    if not sets:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE custom_personas SET %s WHERE id=?" % ",".join("%s=?" % k for k in sets),
        tuple(sets.values()) + (cid,),
    )
    conn.commit()
    conn.close()


def delete_custom_persona(cid: int, user_id: str = None):
    """删角色，连同它的消息和记忆一起删。传 user_id 时校验归属。"""
    conn = get_conn()
    if user_id:
        row = conn.execute(
            "SELECT user_id FROM custom_personas WHERE id=?", (cid,)
        ).fetchone()
        if not row or row[0] != user_id:
            conn.close()
            return False
    key = "custom:%d" % cid
    conn.execute("DELETE FROM messages WHERE persona=?", (key,))
    conn.execute("DELETE FROM memories WHERE persona=?", (key,))
    conn.execute("DELETE FROM milestones WHERE persona=?", (key,))
    conn.execute("DELETE FROM user_characters WHERE persona=?", (key,))
    conn.execute("DELETE FROM custom_personas WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return True


def set_character_baseline(user_id: str, persona: str,
                           intimacy: int = 0, trust: float = 0.0,
                           emotion: float = 0.0):
    """直接设定角色关系的初始值（不走增量）。

    用于新建私有角色：按目标决定她是"早就认识你"还是"刚认识你"。
    """
    get_character_state(user_id, persona)
    conn = get_conn()
    conn.execute(
        "UPDATE user_characters SET intimacy=?, trust=?, emotion_score=?, "
        "relationship_stage=?, updated_at=CURRENT_TIMESTAMP "
        "WHERE user_id=? AND persona=?",
        (max(0, min(100, intimacy)), max(0.0, min(100.0, trust)), emotion,
         "stranger", user_id, persona),
    )
    conn.commit()
    conn.close()



def count_custom_personas(user_id: str) -> int:
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM custom_personas WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return n



# ---- 自定义背景 ----

def set_user_bg(user_id: str, persona: str, file: str, status: str = "pending"):
    """存/覆盖一个角色的背景。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_bg(user_id, persona, file, status) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id, persona) DO UPDATE SET "
        "file=excluded.file, status=excluded.status, created_at=CURRENT_TIMESTAMP",
        (user_id, persona, file, status),
    )
    conn.commit()
    conn.close()


def get_user_bg(user_id: str, persona: str):
    """取一个角色的自定义背景（只返回已通过的）。"""
    if not user_id:
        return None
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM user_bg WHERE user_id=? AND persona=? AND status='approved'",
        (user_id, persona),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_user_bg(user_id: str, persona: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT file FROM user_bg WHERE user_id=? AND persona=?", (user_id, persona)
    ).fetchone()
    conn.execute("DELETE FROM user_bg WHERE user_id=? AND persona=?", (user_id, persona))
    conn.commit()
    conn.close()
    return row[0] if row else None


def list_user_bg(user_id: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM user_bg WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]



# ============ 长期任务 ============

def add_quest_points(user_id: str, persona: str, quest: str, points: int) -> int:
    """给一个长期任务加分，返回加完之后的总分。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO quests(user_id, persona, quest, points) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id, persona, quest) DO UPDATE SET "
        "points=points+excluded.points, updated_at=CURRENT_TIMESTAMP",
        (user_id, persona, quest, points),
    )
    conn.commit()
    row = conn.execute(
        "SELECT points FROM quests WHERE user_id=? AND persona=? AND quest=?",
        (user_id, persona, quest),
    ).fetchone()
    conn.close()
    return int(row[0] or 0) if row else points


def get_quest_notified(user_id: str, persona: str, quest: str) -> int:
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT notified FROM quests WHERE user_id=? AND persona=? AND quest=?",
            (user_id, persona, quest),
        ).fetchone()
        conn.close()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def set_quest_notified(user_id: str, persona: str, quest: str, flag: int):
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE quests SET notified=? WHERE user_id=? AND persona=? AND quest=?",
            (flag, user_id, persona, quest),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_quest_points(user_id: str, persona: str, quest: str) -> int:
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT points FROM quests WHERE user_id=? AND persona=? AND quest=?",
            (user_id, persona, quest),
        ).fetchone()
        conn.close()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


# ============ 事件 ============

def add_event(user_id: str, persona: str, etype: str, summary: str = "",
              intensity: int = 1, affection: float = 0.0,
              trust: float = 0.0, emotion: float = 0.0) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO events(user_id, persona, type, summary, intensity, "
        "affection_delta, trust_delta, emotion_delta) VALUES(?,?,?,?,?,?,?,?)",
        (user_id, persona, etype, summary, intensity, affection, trust, emotion),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def list_events(user_id: str, persona: str, limit: int = 30):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE user_id=? AND persona=? ORDER BY id DESC LIMIT ?",
        (user_id, persona, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ 承诺 ============

def add_promise(user_id: str, persona: str, what: str, due_at: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO promises(user_id, persona, what, due_at) VALUES(?,?,?,?)",
        (user_id, persona, what, due_at),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_due_promises(user_id: str, persona: str):
    """已经到期、还没结算的承诺。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM promises WHERE user_id=? AND persona=? AND status='open' "
        "AND due_at <= DATETIME('now') ORDER BY id",
        (user_id, persona),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_promises(user_id: str, persona: str):
    """还没到期的承诺（用来在提示词里提一句）。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM promises WHERE user_id=? AND persona=? AND status='open' "
        "AND due_at > DATETIME('now') ORDER BY id",
        (user_id, persona),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_promise(pid: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE promises SET status=? WHERE id=?", (status, pid))
    conn.commit()
    conn.close()


# ============ 剧情 ============

def create_story(sid: str, user_id: str, city: str, origin: str, days: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO stories(id, user_id, status, city, origin, days) VALUES(?,?,?,?,?,?)",
        (sid, user_id, "pending", city, origin, days),
    )
    conn.commit()
    conn.close()


def update_story(sid: str, **fields):
    """白名单更新。"""
    ok = {"status", "title", "file", "tokens", "cost_yuan", "charged", "error"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in ok:
            sets.append("%s=?" % k)
            vals.append(v)
    if not sets:
        return
    vals.append(sid)
    conn = get_conn()
    conn.execute("UPDATE stories SET %s, updated_at=CURRENT_TIMESTAMP WHERE id=?" % ",".join(sets), vals)
    conn.commit()
    conn.close()


def get_story(sid: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM stories WHERE id=?", (sid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_stories(user_id: str, limit: int = 20):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM stories WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_stories(user_id: str) -> int:
    """已经用掉的次数。

    失败的不算 —— 失败那边会把钱退回去，再占一次次数就太亏了。
    """
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE user_id=? AND status <> 'failed'",
        (user_id,),
    ).fetchone()[0]
    conn.close()
    return n


def delete_story(sid: str, user_id: str):
    conn = get_conn()
    row = conn.execute("SELECT file FROM stories WHERE id=? AND user_id=?", (sid, user_id)).fetchone()
    conn.execute("DELETE FROM stories WHERE id=? AND user_id=?", (sid, user_id))
    conn.commit()
    conn.close()
    return row[0] if row else None

# ================= 消息：软删除 / 引用 =================

def soft_delete_message(message_id, user_id: str) -> bool:
    """软删除：只标记，不真删。只能删自己的。"""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE messages SET deleted_at=CURRENT_TIMESTAMP "
        "WHERE id=? AND user_id=? AND deleted_at IS NULL",
        (message_id, user_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def restore_message(message_id, user_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE messages SET deleted_at=NULL WHERE id=? AND user_id=?",
        (message_id, user_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def get_message(message_id, user_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, role, content, reply_to FROM messages WHERE id=? AND user_id=?",
        (message_id, user_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_recent_messages_full(user_id: str, persona: str, limit: int = 20):
    """带 id / reply_to 的历史，跳过已删除的。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, role, content, reply_to, recalled_at, recalled_by, created_at, attachments "
        "FROM messages "
        "WHERE user_id=? AND persona=? AND deleted_at IS NULL "
        "ORDER BY id DESC LIMIT ?",
        (user_id, persona, limit),
    ).fetchall()
    conn.close()
    out = []
    for r in reversed(rows):
        out.append({"id": r["id"], "role": r["role"], "content": r["content"],
                    "reply_to": r["reply_to"],
                    "recalled_at": r["recalled_at"], "recalled_by": r["recalled_by"],
                    "created_at": r["created_at"], "attachments": r["attachments"]})
    return out

# ================= 消息：撤回 =================

def recall_message(message_id, user_id: str, by: str = "user") -> bool:
    """撤回：留痕但保留原文。只能撤自己的（AI 的用 by='ai' 单独走）。"""
    conn = get_conn()
    if by == "user":
        cur = conn.execute(
            "UPDATE messages SET recalled_at=CURRENT_TIMESTAMP, recalled_by='user' "
            "WHERE id=? AND user_id=? AND role='user' AND recalled_at IS NULL",
            (message_id, user_id),
        )
    else:
        cur = conn.execute(
            "UPDATE messages SET recalled_at=CURRENT_TIMESTAMP, recalled_by='ai' "
            "WHERE id=? AND user_id=? AND role='assistant' AND recalled_at IS NULL",
            (message_id, user_id),
        )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def get_last_recall(user_id: str, persona: str, within_seconds: int = 900):
    """最近一次撤回（给 prompt 注入用）。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, role, content, recalled_by, recalled_at FROM messages "
        "WHERE user_id=? AND persona=? AND recalled_at IS NOT NULL "
        "AND (strftime('%s','now') - strftime('%s', recalled_at)) <= ? "
        "ORDER BY recalled_at DESC LIMIT 1",
        (user_id, persona, within_seconds),
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_last_assistant_id(user_id: str, persona: str):
    """最后一条她说的（用于她自己撤回）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM messages WHERE user_id=? AND persona=? AND role='assistant' "
        "AND recalled_at IS NULL ORDER BY id DESC LIMIT 1",
        (user_id, persona),
    ).fetchone()
    conn.close()
    return row[0] if row else None
