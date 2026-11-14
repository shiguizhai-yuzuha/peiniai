# -*- coding: utf-8 -*-
"""数据库整理：把 users 里的历史好感/表白同步到 user_characters，并补齐缺失的角色行。

默认只预览，加 --apply 才真正写库。不删除任何数据。

用法：
    python -X utf8 fix_db.py                      # 预览
    python -X utf8 fix_db.py --apply              # 执行
    python -X utf8 fix_db.py --report rep.json    # 同时存一份 JSON 报告
"""

import argparse
import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import get_conn

DEFAULT_PERSONA = "流萤"


def main(argv):
    ap = argparse.ArgumentParser(description="整理 love_bot 数据库（只补不删）")
    ap.add_argument("--apply", action="store_true", help="真正写库")
    ap.add_argument("--report", help="把报告另存为 JSON")
    a = ap.parse_args(argv)

    conn = get_conn()
    cur = conn.cursor()

    users = [dict(r) for r in cur.execute("SELECT * FROM users")]
    report = {
        "mode": "apply" if a.apply else "preview",
        "missing_character_rows": [],
        "intimacy_sync": [],
        "confessed_sync": [],
    }

    for u in users:
        uid = u["user_id"]
        name = u["username"]
        row = cur.execute(
            "SELECT * FROM user_characters WHERE user_id=? AND persona=?",
            (uid, DEFAULT_PERSONA),
        ).fetchone()

        # 1) 缺流萤这行 → 从 users 补一行
        if not row:
            u_int = u.get("intimacy") or 0
            if u_int > 0 or u.get("confessed_at"):
                report["missing_character_rows"].append({
                    "username": name, "intimacy": u_int,
                    "confessed_at": u.get("confessed_at"),
                })
                if a.apply:
                    cur.execute(
                        "INSERT OR IGNORE INTO user_characters"
                        "(user_id, persona, intimacy, relationship_stage, confessed_at, emotion_score) "
                        "VALUES(?,?,?,?,?,?)",
                        (uid, DEFAULT_PERSONA, u_int,
                         u.get("relationship_stage") or "stranger",
                         u.get("confessed_at"), u.get("emotion_score") or 0),
                    )
            continue

        # 2) users 里的好感比 user_characters 高 → 同步过来（旧代码一直写的是 users）
        uc_int = row["intimacy"] or 0
        u_int = u.get("intimacy") or 0
        if u_int > uc_int + 0.001:
            report["intimacy_sync"].append({
                "username": name, "from": round(uc_int, 2), "to": round(u_int, 2),
            })
            if a.apply:
                cur.execute(
                    "UPDATE user_characters SET intimacy=? WHERE user_id=? AND persona=?",
                    (round(u_int, 2), uid, DEFAULT_PERSONA),
                )

        # 3) users 里有表白记录但 user_characters 没有 → 补上
        if u.get("confessed_at") and not row["confessed_at"]:
            report["confessed_sync"].append({
                "username": name, "confessed_at": u["confessed_at"],
            })
            if a.apply:
                cur.execute(
                    "UPDATE user_characters SET confessed_at=?, relationship_stage='lover' "
                    "WHERE user_id=? AND persona=?",
                    (u["confessed_at"], uid, DEFAULT_PERSONA),
                )

    if a.apply:
        conn.commit()

    report["counts"] = {
        t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("users", "messages", "memories", "user_characters")
    }

    # 疑似测试账号（只报告，不删）
    suspects = []
    for u in users:
        n = cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?",
                        (u["user_id"],)).fetchone()[0]
        uname = u["username"] or ""
        # 只按"几乎没聊过"判定，不看用户名长度（免得把 fgv 这种真实用户算进来）
        looks_test = n <= 6 and (u.get("total_tokens") or 0) < 5000
        if looks_test:
            suspects.append({
                "username": uname, "messages": n,
                "tokens": u.get("total_tokens") or 0,
                "balance": round(u.get("balance") or 0, 3),
            })
    report["suspect_test_accounts"] = suspects

    conn.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("\n报告已存:", a.report)
    if not a.apply:
        print("\n（预览模式，没有写库。确认无误后加 --apply）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
