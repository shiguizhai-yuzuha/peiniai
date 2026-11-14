# -*- coding: utf-8 -*-
"""审核用户上传的背景图

用法：
   python 审核背景.py                 看所有待审的
   python 审核背景.py approve 3       通过第 3 条
   python 审核背景.py reject 3        拒绝第 3 条
   python 审核背景.py list            看已经通过的
"""
import os
import sys

import sqlite3

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "love_bot.db")


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def show(status="pending"):
    c = conn()
    rows = c.execute(
        "SELECT b.*, u.username FROM user_bg b LEFT JOIN users u ON u.user_id=b.user_id "
        "WHERE b.status=? ORDER BY b.created_at", (status,)
    ).fetchall()
    c.close()

    if not rows:
        print(f"没有 {status} 的图。")
        return

    print(f"=== {status}（{len(rows)} 条）===")
    for r in rows:
        size = "?"
        if r["file"] and os.path.exists(r["file"]):
            size = "%.0fKB" % (os.path.getsize(r["file"]) / 1024)
        else:
            size = "文件不见了"
        print()
        print(f"  [{r['id']}]  {r['username']}  换的是「{r['persona']}」  {size}")
        print(f"        {r['file']}")
        print(f"        传于 {r['created_at']}")
    print()
    if status == "pending":
        print("看完图之后：")
        print("   通过  python 审核背景.py approve <编号>")
        print("   拒绝  python 审核背景.py reject  <编号>")
    else:
        print("这些都已经在用了。想撤掉一个：")
        print("   python 审核背景.py reject <编号>")


def set_status(bid, status):
    c = conn()
    row = c.execute("SELECT * FROM user_bg WHERE id=?", (bid,)).fetchone()
    if not row:
        print(f"没有编号 {bid} 的记录")
        c.close()
        return
    c.execute("UPDATE user_bg SET status=? WHERE id=?", (status, bid))
    c.commit()
    c.close()

    if status == "rejected" and row["file"] and os.path.exists(row["file"]):
        try:
            os.remove(row["file"])
        except Exception:
            pass

    print(f"[{bid}] {row['persona']} → {status}")
    if status == "approved":
        print("  用户切到那个角色就能看到了。")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        show("pending")
    elif len(sys.argv) >= 2 and sys.argv[1] == "list":
        show("approved")
    elif len(sys.argv) >= 3 and sys.argv[1] == "approve":
        set_status(int(sys.argv[2]), "approved")
    elif len(sys.argv) >= 3 and sys.argv[1] == "reject":
        set_status(int(sys.argv[2]), "rejected")
    else:
        print(__doc__)
