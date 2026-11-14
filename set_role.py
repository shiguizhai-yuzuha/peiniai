import sqlite3
import sys

ROLES = ("user", "vip", "admin", "banned")

if len(sys.argv) < 3:
    print("用法：python set_role.py <用户名或用户ID> <user|vip|admin|banned> [备注]")
    print("例子：python set_role.py XIAO2026 admin 站长")
    print("      python set_role.py fgv vip")
    sys.exit()

target = sys.argv[1]
role = sys.argv[2]
note = sys.argv[3] if len(sys.argv) > 3 else None

if role not in ROLES:
    print(f"❌ 角色只能是 {' / '.join(ROLES)}")
    sys.exit()

conn = sqlite3.connect("love_bot.db")
cur = conn.cursor()

# 用户名或 user_id 都能匹配，中文名传参出问题时用 ID 更稳
cur.execute("SELECT username, role FROM users WHERE username=? OR user_id=?", (target, target))
row = cur.fetchone()
if not row:
    print(f"❌ 找不到用户：{target}")
    conn.close()
    sys.exit()

name, old = row
if note:
    cur.execute("UPDATE users SET role=?, note=? WHERE username=?", (role, note, name))
else:
    cur.execute("UPDATE users SET role=? WHERE username=?", (role, name))
conn.commit()

print(f"✅ {name}: {old or 'user'} → {role}" + (f"（{note}）" if note else ""))
print()
print("当前用户：")
for r in cur.execute(
    "SELECT username, role, balance, note FROM users ORDER BY rowid DESC LIMIT 15"
):
    print(f"   {r[0]:<20} {r[1]:<7} 余额 {r[2]:>8.2f}  {r[3] or ''}")

conn.close()
