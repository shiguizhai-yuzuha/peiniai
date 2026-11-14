# -*- coding: utf-8 -*-
"""用户数据导出接口（只读）。

全部是纯函数：返回 dict / list，不写文件。
真正落盘的是 export_user / export_all 两个封装。

命令行：
    python -X utf8 services/export.py --list
    python -X utf8 services/export.py --user XIAO2026 --out D:\\导出
    python -X utf8 services/export.py --all --out D:\\导出 --no-messages

作为模块用：
    from services.export import build_profile, export_user
    data = build_profile(user_id)
"""

import json
import os
import re
import sys
from collections import Counter

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import repository as repo
from db.database import get_conn
from core import relationship

SCHEMA_VERSION = 1

# 官方进价（元 / 百万 token），只用于"估算成本"，不是售价
_PRICE_IN = 2.0
_PRICE_OUT = 8.0

_STOP_CHARS = set("的了是我你他她它们这那就都也还在有和吗呢吧啊哦嗯呀么不没很个上下来去说过要会能想")


# ============ 基础查询 ============

def list_users():
    """库里所有账号（导出清单用）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, username, created_at, balance, total_tokens "
        "FROM users ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_user_id(username: str):
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return row["user_id"] if row else None


# ============ 各个分块 ============

def _stage_label(stage: str, is_lover: bool) -> str:
    if is_lover:
        return relationship.STAGE_NAMES.get("lover", "恋爱后")
    return relationship.STAGE_NAMES.get(stage, stage or "未知")


def build_account(user_id: str) -> dict:
    user = repo.get_or_create_user(user_id)
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "nickname": user.get("nickname"),
        "registered_at": user.get("created_at"),
        "last_active_at": user.get("last_active_at"),
        "balance": round(user.get("balance") or 0, 4),
        "total_tokens": user.get("total_tokens") or 0,
    }


def build_characters(user_id: str) -> list:
    """每个角色一条：好感、阶段、表白、情绪、聊了多少、最后一次。"""
    out = []
    for row in repo.get_all_characters(user_id):
        persona = row.get("persona")
        char = repo.get_character_state(user_id, persona)
        is_lover = bool(char.get("confessed_at"))
        msgs = repo.get_all_messages(user_id, persona)
        out.append({
            "persona": persona,
            "intimacy": round(char.get("intimacy") or 0, 2),
            "stage": char.get("relationship_stage"),
            "stage_label": _stage_label(char.get("relationship_stage"), is_lover),
            "confessed_at": char.get("confessed_at"),
            "emotion_score": round(char.get("emotion_score") or 0, 3),
            "message_count": len(msgs),
            "last_talked_at": msgs[-1]["created_at"] if msgs else None,
        })
    out.sort(key=lambda x: x.get("intimacy") or 0, reverse=True)
    return out


def build_memories(user_id: str) -> list:
    return [dict(m) for m in repo.get_all_memories(user_id)]


def build_stats(user_id: str, persona: str = None) -> dict:
    msgs = repo.get_all_messages(user_id, persona)
    if not msgs:
        return {"total_messages": 0}
    user_msgs = [m for m in msgs if m["role"] == "user"]
    days = sorted({str(m["created_at"])[:10] for m in msgs})
    lengths = [len(m["content"] or "") for m in user_msgs]
    return {
        "total_messages": len(msgs),
        "user_messages": len(user_msgs),
        "assistant_messages": len(msgs) - len(user_msgs),
        "first_at": msgs[0]["created_at"],
        "last_at": msgs[-1]["created_at"],
        "active_days": len(days),
        "total_chars_from_user": sum(lengths),
        "avg_chars_per_user_msg": round(sum(lengths) / max(1, len(lengths)), 1),
        "longest_user_msg": max(lengths) if lengths else 0,
    }


def build_keywords(user_id: str, persona: str = None, top: int = 20) -> list:
    """粗粒度话题词：中文二元组词频（没上分词库，够用就行）。"""
    text = "".join(
        (m["content"] or "")
        for m in repo.get_all_messages(user_id, persona)
        if m["role"] == "user"
    )
    text = re.sub(r"[^\u4e00-\u9fa5]", " ", text)
    counter = Counter()
    for seg in text.split():
        for i in range(len(seg) - 1):
            pair = seg[i:i + 2]
            if pair[0] in _STOP_CHARS and pair[1] in _STOP_CHARS:
                continue
            counter[pair] += 1
    return [{"word": w, "count": n} for w, n in counter.most_common(top)]


def build_billing(user_id: str) -> dict:
    user = repo.get_or_create_user(user_id)
    tokens = user.get("total_tokens") or 0
    # 只有总 token，没有输入/输出拆分，按 85/15 粗估
    cost = tokens * 0.85 / 1e6 * _PRICE_IN + tokens * 0.15 / 1e6 * _PRICE_OUT
    return {
        "total_tokens": tokens,
        "balance": round(user.get("balance") or 0, 4),
        "estimated_cost_cny": round(cost, 4),
        "price_in_per_million": _PRICE_IN,
        "price_out_per_million": _PRICE_OUT,
    }


def build_conversation(user_id: str, persona: str = None) -> list:
    return [
        {
            "id": m["id"],
            "at": m["created_at"],
            "persona": m["persona"],
            "role": m["role"],
            "content": m["content"],
            "tokens": m["tokens"],
        }
        for m in repo.get_all_messages(user_id, persona)
    ]


# ============ 组装 ============

def build_profile(user_id: str, with_keywords: bool = True) -> dict:
    """完整用户画像。"""
    profile = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "account": build_account(user_id),
        "characters": build_characters(user_id),
        "memories": build_memories(user_id),
        "milestones": repo.get_milestones(user_id),
        "stats": build_stats(user_id),
        "billing": build_billing(user_id),
    }
    if with_keywords:
        profile["keywords"] = build_keywords(user_id)
    return profile


def build_prompt_context(user_id: str, persona: str, limit_memories: int = 6) -> str:
    """给 prompt 用的轻量摘要（比 build_profile 便宜得多）。"""
    char = repo.get_character_state(user_id, persona)
    is_lover = bool(char.get("confessed_at"))
    stats = build_stats(user_id, persona)
    memories = repo.get_memories(user_id, persona, limit=limit_memories)
    lines = [
        "## 用户快照",
        f"和你的关系：{_stage_label(char.get('relationship_stage'), is_lover)}"
        f"（好感 {round(char.get('intimacy') or 0)}）",
        f"跟你的对话：{stats.get('total_messages', 0)} 条，"
        f"跨 {stats.get('active_days', 0)} 天",
    ]
    if memories:
        lines.append("他提过的事：")
        lines += [f"- {m['key']}: {m['value']}" for m in memories]
    return "\n".join(lines)


# ============ 落盘 ============

def _write_json(path: str, obj) -> str:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def export_user(user_id: str, out_dir: str, with_messages: bool = True) -> list:
    """导出一个用户：画像 + （可选）完整对话。返回写入的文件列表。"""
    user = repo.get_or_create_user(user_id)
    name = user.get("username") or (user_id or "unknown")[:8]
    files = [_write_json(os.path.join(out_dir, f"{name}_profile.json"),
                         build_profile(user_id))]
    if with_messages:
        files.append(_write_json(os.path.join(out_dir, f"{name}_messages.json"),
                                 build_conversation(user_id)))
    return files


def export_all(out_dir: str, with_messages: bool = True) -> list:
    files = []
    for u in list_users():
        try:
            files += export_user(u["user_id"], out_dir, with_messages)
        except Exception as e:
            print(f"[跳过] {u.get('username')}: {e}", file=sys.stderr)
    return files


# ============ CLI ============

def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="导出用户画像 / 对话 / 记忆")
    ap.add_argument("--user", help="用户名")
    ap.add_argument("--all", action="store_true", help="导出全部用户")
    ap.add_argument("--out", default="exports", help="输出目录（默认 ./exports）")
    ap.add_argument("--no-messages", action="store_true", help="不导出对话全文")
    ap.add_argument("--list", action="store_true", help="只列出用户")
    a = ap.parse_args(argv)

    if a.list:
        for u in list_users():
            print(f"{u['username'] or '?':<20} {u['user_id']}  {u['created_at']}")
        return 0

    if a.all:
        files = export_all(a.out, not a.no_messages)
        print(f"写完了：{len(files)} 个文件 → {os.path.abspath(a.out)}")
        return 0

    if not a.user:
        ap.print_help()
        return 1

    uid = find_user_id(a.user)
    if not uid:
        print("找不到用户:", a.user)
        return 2
    for f in export_user(uid, a.out, not a.no_messages):
        print("写入:", f)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
