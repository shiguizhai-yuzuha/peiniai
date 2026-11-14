import sqlite3
import sys

if len(sys.argv) < 3:
    print("用法：python add_balance.py <用户名> <金额>")
    sys.exit()

username = sys.argv[1]
amount = float(sys.argv[2])

conn = sqlite3.connect("love_bot.db")
cur = conn.cursor()

cur.execute("SELECT balance FROM users WHERE username=?", (username,))
row = cur.fetchone()
if not row:
    print(f"❌ 用户 {username} 不存在")
    conn.close()
    sys.exit()

old = row[0]
new = old + amount

conn.execute("UPDATE users SET balance=? WHERE username=?", (new, username))
conn.commit()
conn.close()

print(f"✅ {username}: {old:.4f} → {new:.4f} 元（{amount:+.4f}）")