# -*- coding: utf-8 -*-
"""把已写入的纪念，时间纠偏成"真正发生的那天"。

背景：早期是补录的，unlocked_at 全变成了写库当天（2026-10-20）。
这个脚本按消息历史重算一遍。只 UPDATE 时间，不增删记录。

用法：
    python -X utf8 fix_milestones.py
"""

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import get_conn
from core import milestones


def main():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT user_id, persona FROM milestones"
    ).fetchall()
    conn.close()

    if not rows:
        print("库里还没有纪念记录。")
        return 0

    total = 0
    for r in rows:
        uid, persona = r["user_id"], r["persona"]
        n = milestones.sync_dates(uid, persona)
        total += n
        print(f"  {uid[:8]}… / {persona}: 更新 {n} 条")

    print(f"\n合计更新 {total} 条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
