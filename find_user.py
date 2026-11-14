import sys
import sqlite3

prefix = sys.argv[1] if len(sys.argv) > 1 else "f5d4615f"

conn = sqlite3.connect("love_bot.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute(
    "SELECT * FROM users WHERE user_id LIKE ?",
    (prefix + "%",),
)
row = cur.fetchone()

if not row:
    print(f"没找到 user_id 以 {prefix} 开头的用户")
    conn.close()
    sys.exit()

u = dict(row)
print("=" * 50)
print(f"用户名      : {u.get('username')}")
print(f"昵称        : {u.get('nickname')}")
print(f"user_id     : {u.get('user_id')}")
print(f"人设        : {u.get('persona')}")
print(f"好感度      : {u.get('intimacy')}")
print(f"关系阶段    : {u.get('relationship_stage')}")
print(f"表白时间    : {u.get('confessed_at')}")
print(f"情绪分      : {u.get('emotion_score')}")
print(f"余额        : {u.get('balance')}")
print(f"总 token    : {u.get('total_tokens')}")
print(f"最后活跃    : {u.get('last_active_at')}")
print(f"注册时间    : {u.get('created_at')}")
print("=" * 50)

# 顺手带一下消息数和记忆数
cur.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (u.get("user_id"),))
msg_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM memories WHERE user_id=?", (u.get("user_id"),))
mem_count = cur.fetchone()[0]
print(f"消息数      : {msg_count}")
print(f"记忆数      : {mem_count}")

conn.close()