import sqlite3
import sys

# 可选：python stats.py love_bot.bak   （不填默认 love_bot.db）
db_path = sys.argv[1] if len(sys.argv) > 1 else "love_bot.db"

c = sqlite3.connect(db_path)
c.row_factory = sqlite3.Row

print(f"库文件：{db_path}")

n_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
n_msgs = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
n_mem = c.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
n_ms = c.execute("SELECT COUNT(*) FROM milestones").fetchone()[0]
bal = c.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0]

print("=" * 58)
print(f"用户总数 : {n_users}")
print(f"消息总数 : {n_msgs}")
print(f"记忆条数 : {n_mem}")
print(f"纪念解锁 : {n_ms}")
print(f"余额合计 : {bal:.2f} 元")
print("=" * 58)

print("\n按身份：")
for r in c.execute("SELECT COALESCE(role,'user') AS r, COUNT(*) n FROM users GROUP BY r ORDER BY n DESC"):
    print(f"   {r['r']:<8} {r['n']} 人")

print("\n全部用户（按消息数排序）：")
print(f"   {'用户名':<20}{'身份':<8}{'余额':>9}{'消息':>7}")
print("   " + "-" * 52)
for r in c.execute("""
    SELECT u.username, COALESCE(u.role,'user') AS role, u.balance,
           (SELECT COUNT(*) FROM messages m WHERE m.user_id = u.user_id) AS n
    FROM users u
    ORDER BY n DESC
"""):
    print(f"   {r['username']:<20}{r['role']:<8}{r['balance']:>9.2f}{r['n']:>7}")

print("\n活跃度分档：")
for label, lo, hi in [("一句话都没有", 0, 0), ("聊了几句（1-10）", 1, 10),
                      ("聊得下去（11-100）", 11, 100), ("重度（100+）", 101, 10 ** 9)]:
    n = c.execute("""
        SELECT COUNT(*) FROM users u
        WHERE (SELECT COUNT(*) FROM messages m WHERE m.user_id = u.user_id) BETWEEN ? AND ?
    """, (lo, hi)).fetchone()[0]
    print(f"   {label:<20} {n} 人")

c.close()
