import sys
from db.database import get_conn

if len(sys.argv) < 2:
    print("用法：python who.py 用户名")
    sys.exit()

username = sys.argv[1]

conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT user_id, username, intimacy FROM users WHERE username=?", (username,))
row = cur.fetchone()
conn.close()

if not row:
    print(f"没找到用户：{username}")
else:
    print(f"用户名: {row['username']}")
    print(f"user_id: {row['user_id']}")
    print(f"好感度: {row['intimacy']}")
    print(f"\n复制这一行去用：")
    print(f"python -c \"from db.repository import get_character_state; print(get_character_state('{row['user_id']}', '流萤'))\"")