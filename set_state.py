import sqlite3
import sys

# 用法：python set_state.py 30 familiar
# 用法：python set_state.py 85 close

intimacy = float(sys.argv[1]) if len(sys.argv) > 1 else 30
stage = sys.argv[2] if len(sys.argv) > 2 else "familiar"

conn = sqlite3.connect("love_bot.db")
conn.execute(
    "UPDATE users SET intimacy=?, relationship_stage=?, confessed_at=NULL",
    (intimacy, stage),
)
conn.commit()
conn.close()
print(f"OK：好感度={intimacy}, 关系阶段={stage}")