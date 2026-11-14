import sqlite3

conn = sqlite3.connect("love_bot.db")
cur = conn.cursor()
cur.execute("""
SELECT u.username, u.intimacy, u.relationship_stage, u.balance,
       (SELECT COUNT(*) FROM messages m WHERE m.user_id = u.user_id) as msg_count,
       (SELECT COUNT(*) FROM memories me WHERE me.user_id = u.user_id) as mem_count
FROM users u ORDER BY u.intimacy DESC
""")

print(f"{'用户名':<12} {'好感度':<8} {'关系':<10} {'余额':<8} {'消息数':<6} {'记忆数'}")
print("-" * 70)
for r in cur.fetchall():
    print(f"{r[0]:<12} {r[1]:<8.1f} {r[2]:<10} {r[3]:<8.2f} {r[4]:<6} {r[5]}")

conn.close()
