import sys, os, sqlite3
sys.path.insert(0, "/opt/mybot"); os.chdir("/opt/mybot")
from core import memory
c = sqlite3.connect("/opt/mybot/love_bot.db"); c.row_factory = sqlite3.Row
u = c.execute("SELECT user_id FROM users WHERE username=?", ("刘了凡",)).fetchone()[0]
c.close()
j = "\n".join(m.get("content") or "" for m in memory.build_messages(u, "浮波柚叶", user_text="好吃吗"))
print("  含生日彩蛋:", "今天是你生日。你不会主动说这件事" in j)
print("  含次日回响:", "昨天是你生日" in j)
print("  含降级提示:", "今天你已经说过一遍" in j)
