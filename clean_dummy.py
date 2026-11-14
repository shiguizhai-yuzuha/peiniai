import sqlite3

conn = sqlite3.connect("love_bot.db")
cur = conn.cursor()

# 删掉刚才用 username 当 user_id 建的假记录
cur.execute("DELETE FROM user_characters WHERE user_id = 'XIAO2026'")
deleted = cur.rowcount
conn.commit()

# 看结果
cur.execute("SELECT user_id, persona, intimacy FROM user_characters")
rows = cur.fetchall()
print(f"删除了 {deleted} 条脏数据")
print(f"user_characters 现在有 {len(rows)} 条：")
for r in rows:
    print(f"  {r[0][:8]}... | {r[1]} | 好感度 {r[2]}")

conn.close()