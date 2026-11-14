import gradio as gr
import sqlite3
import os
from datetime import datetime, timedelta

ADMIN_PASSWORD = "admin123"  # 自己改

# 数据库绝对路径，保证不管从哪启动都连同一个库
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "love_bot.db")


def to_local(ts):
    """把 SQLite 的 UTC 时间戳转成北京时间字符串"""
    if not ts:
        return ""
    try:
        dt = datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S")
        return (dt + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def check(pwd):
    return pwd == ADMIN_PASSWORD


def load_users(pwd):
    if not check(pwd):
        return "密码错误"
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    SELECT u.username, c.persona, c.intimacy, c.relationship_stage, c.confessed_at,
           u.balance, u.total_tokens,
           (SELECT COUNT(*) FROM messages m
             WHERE m.user_id = u.user_id AND m.persona = c.persona) as msg_count
    FROM users u
    LEFT JOIN user_characters c ON c.user_id = u.user_id
    ORDER BY u.username, c.intimacy DESC
    """)
    rows = cur.fetchall()
    conn.close()

    lines = []
    lines.append(f"共 {len(rows)} 行（用户 × 角色）\n")
    lines.append(f"{'用户名':<12} {'角色':<10} {'好感度':<8} {'阶段':<10} {'已表白':<6} {'余额':<8} {'消息数':<6}")
    lines.append("-" * 80)
    for r in rows:
        username, cpersona, intimacy, stage, confessed, balance, tokens, msg_count = r
        intimacy = intimacy or 0
        balance = balance or 0
        confessed_str = "是" if confessed else "否"
        lines.append(
            f"{username or '':<12} {cpersona or '':<10} {intimacy:<8.1f} {stage or '':<10} "
            f"{confessed_str:<6} {balance:<8.2f} {msg_count:<6}"
        )
    return "\n".join(lines)


def load_messages(pwd, username):
    if not check(pwd):
        return "密码错误"
    if not username.strip():
        return "请输入用户名"
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return f"用户 {username} 不存在"
    user_id = row[0]
    cur.execute("""
    SELECT role, content, created_at, persona FROM messages
    WHERE user_id=? ORDER BY id DESC LIMIT 50
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    lines = [f"{username} 最近 50 条消息（北京时间）：\n"]
    for role, content, created, mpersona in reversed(rows):
        role_label = "用户" if role == "user" else (mpersona or "AI")
        lines.append(f"[{to_local(created)}] {role_label}: {content}")
    return "\n".join(lines)


def load_memories(pwd, username):
    if not check(pwd):
        return "密码错误"
    if not username.strip():
        return "请输入用户名"
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return f"用户 {username} 不存在"
    user_id = row[0]
    cur.execute("""
    SELECT key, value, priority, updated_at FROM memories
    WHERE user_id=? ORDER BY priority DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return f"{username} 还没有记忆"
    lines = [f"{username} 的记忆：\n"]
    for key, value, priority, updated in rows:
        lines.append(f"[优先级{priority}] {key}: {value}  ({to_local(updated)})")
    return "\n".join(lines)


def load_milestones(pwd, username):
    if not check(pwd):
        return "密码错误"
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if username.strip():
        cur.execute("SELECT user_id FROM users WHERE username=?", (username.strip(),))
        row = cur.fetchone()
        if not row:
            conn.close()
            return f"用户 {username} 不存在"
        rows = cur.execute(
            "SELECT persona, title, unlocked_at FROM milestones "
            "WHERE user_id=? ORDER BY unlocked_at", (row["user_id"],)
        ).fetchall()
        head = f"{username} 的纪念：\n"
        with_who = False
    else:
        rows = cur.execute(
            "SELECT u.username, m.persona, m.title, m.unlocked_at FROM milestones m "
            "LEFT JOIN users u ON u.user_id = m.user_id ORDER BY m.unlocked_at"
        ).fetchall()
        head = "全部纪念：\n"
        with_who = True
    conn.close()

    if not rows:
        return head + "（还没有）"

    lines = [head]
    for r in rows:
        who = (r["username"] or "?") + " / " if with_who else ""
        lines.append(f"[{to_local(r['unlocked_at'])}] {who}{r['persona']}：{r['title']}")
    return "\n".join(lines)


def load_overview(pwd):
    if not check(pwd):
        return "密码错误"
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM messages")
    msg_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM messages WHERE role='user'")
    user_msg = cur.fetchone()[0]

    cur.execute("SELECT SUM(total_tokens) FROM users")
    total_tokens = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM users WHERE confessed_at IS NOT NULL")
    lover_count = cur.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "SELECT COUNT(*) FROM messages WHERE DATE(created_at)=?",
        (today,)
    )
    today_msg = cur.fetchone()[0]

    conn.close()

    return (
        f"数据库文件：{DB_FILE}\n"
        f"总用户数：{user_count}\n"
        f"总消息数：{msg_count}（用户发出 {user_msg} 条）\n"
        f"今日消息数：{today_msg}\n"
        f"总 token 消耗：{total_tokens}\n"
        f"已进入恋人的用户：{lover_count}\n"
    )


with gr.Blocks(title="后台") as demo:
    gr.Markdown("# 🎛️ 流萤后台")
    pwd = gr.Textbox(label="管理员密码", type="password", value="")

    with gr.Tab("总览"):
        overview_btn = gr.Button("刷新总览")
        overview_out = gr.Textbox(label="数据", lines=10)
        overview_btn.click(load_overview, [pwd], [overview_out])

    with gr.Tab("用户列表"):
        users_btn = gr.Button("刷新用户列表")
        users_out = gr.Textbox(label="用户", lines=20)
        users_btn.click(load_users, [pwd], [users_out])

    with gr.Tab("聊天记录"):
        msg_username = gr.Textbox(label="用户名")
        msg_btn = gr.Button("查看聊天记录")
        msg_out = gr.Textbox(label="消息", lines=30)
        msg_btn.click(load_messages, [pwd, msg_username], [msg_out])

    with gr.Tab("记忆"):
        mem_username = gr.Textbox(label="用户名")
        mem_btn = gr.Button("查看记忆")
        mem_out = gr.Textbox(label="记忆", lines=30)
        mem_btn.click(load_memories, [pwd, mem_username], [mem_out])

    with gr.Tab("纪念"):
        ms_username = gr.Textbox(label="用户名（留空=全部）")
        ms_btn = gr.Button("查看纪念")
        ms_out = gr.Textbox(label="纪念", lines=30)
        ms_btn.click(load_milestones, [pwd, ms_username], [ms_out])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7865)