import sqlite3

conn = sqlite3.connect("love_bot.db")
cur = conn.cursor()
cur.execute("""
SELECT m.username, me.persona, me.key, me.value, me.priority
FROM memories me
JOIN users m ON m.user_id = me.user_id
ORDER BY m.username, me.persona, me.priority DESC
""")
rows = cur.fetchall()

print(f"{'用户':<15} {'角色':<8} {'键':<20} {'值':<30} {'优先级'}")
print("-" * 90)
for r in rows:
    print(f"{r[0]:<15} {r[1]:<8} {r[2]:<20} {r[3]:<30} {r[4]}")

if not rows:
    print("（暂无记忆）")

conn.close()