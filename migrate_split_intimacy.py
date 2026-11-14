import sqlite3

conn = sqlite3.connect("love_bot.db")
cur = conn.cursor()

# 1. 建新表
cur.execute("""
CREATE TABLE IF NOT EXISTS user_characters (
    user_id TEXT,
    persona TEXT,
    intimacy INTEGER DEFAULT 0,
    relationship_stage TEXT DEFAULT 'stranger',
    confessed_at TIMESTAMP,
    emotion_score REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, persona)
)
""")

# 2. 把现有用户的好感度搬过去，默认给"流萤"
cur.execute("SELECT user_id, intimacy, relationship_stage, confessed_at, emotion_score FROM users")
rows = cur.fetchall()
for r in rows:
    user_id, intimacy, stage, confessed, emotion = r
    cur.execute("""
    INSERT OR IGNORE INTO user_characters
    (user_id, persona, intimacy, relationship_stage, confessed_at, emotion_score)
    VALUES (?, '流萤', ?, ?, ?, ?)
    """, (user_id, intimacy or 0, stage or 'stranger', confessed, emotion or 0))

conn.commit()
print(f"迁移完成，共 {len(rows)} 个用户")

# 3. 验证
cur.execute("SELECT COUNT(*) FROM user_characters")
print(f"user_characters 表有 {cur.fetchone()[0]} 条记录")

conn.close()