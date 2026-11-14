import sqlite3

conn = sqlite3.connect("love_bot.db")
conn.execute("DELETE FROM messages")
conn.execute("DELETE FROM memories")
conn.execute("UPDATE users SET intimacy=0, relationship_stage='stranger', confessed_at=NULL")
conn.commit()
conn.close()
print("聊天记录、记忆、关系已清空，账号保留")