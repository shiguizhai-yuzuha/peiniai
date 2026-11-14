from datetime import datetime, timezone

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def get_time_context(last_active_at) -> dict:
    now = datetime.now()
    hour = now.hour

    # 时段判定
    if 6 <= hour < 11:
        period = "早晨"
        period_hint = "你刚醒，话不多，可以轻轻问一句'早，睡好了吗'。"
    elif 11 <= hour < 14:
        period = "中午"
        period_hint = "正常节奏，不用特别提醒。"
    elif 14 <= hour < 18:
        period = "下午"
        period_hint = "正常节奏，不用特别提醒。"
    elif 18 <= hour < 22:
        period = "傍晚"
        period_hint = "放松一点，可以问'今天怎么样'。"
    else:
        period = "深夜"
        period_hint = (
            "语气轻，不要主动开新话题，可以提醒对方早点睡。"
            "现在是深夜（凌晨），不要再提'晚上再说''等天黑''晚上再去'这类话——现在就是夜里。"
        )

    # 距上次对话
    # ⚠️ last_active_at 是 SQLite 的 CURRENT_TIMESTAMP，也就是 UTC。
    # 而 datetime.now() 是本地时间（北京）。
    # 直接相减会多算 8 小时，把"今天早上"算成"昨天"。
    hours_since = -1
    if last_active_at:
        try:
            last = datetime.fromisoformat(str(last_active_at))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        except Exception:
            hours_since = -1

    # 相对时间描述 + 防幻觉
    if hours_since < 0:
        first_time = True
        rel_text = "这是你们第一次对话。"
        avoid = "首次对话，不要提'上次''昨天''之前'。"
    elif hours_since < 1:
        first_time = False
        rel_text = f"距上次对话：约{int(hours_since * 60)}分钟。"
        avoid = "刚聊过不久，不要说'好久没聊'，也不要说'昨天'。"
    elif hours_since < 4:
        first_time = False
        rel_text = f"距上次对话：约{int(hours_since)}小时。"
        avoid = "刚聊过不久，不要说'好久没聊'，也不要说'昨天'。"
    elif hours_since < 24:
        first_time = False
        rel_text = f"距上次对话：约{int(hours_since)}小时。"
        avoid = "距上次不到一天，说'今天'或'刚才'，不要说'昨天'。"
    elif hours_since < 48:
        first_time = False
        rel_text = f"距上次对话：约{int(hours_since / 24)}天。"
        avoid = "距上次过了一天，可以说'昨天'。"
    else:
        first_time = False
        days = int(hours_since / 24)
        rel_text = f"距上次对话：约{days}天。"
        avoid = f"距上次对话{days}天，可以说'好久没聊'。"

    time_str = (
        f"{now.year}年{now.month}月{now.day}日，"
        f"{WEEKDAYS[now.weekday()]}，{hour}点{now.minute:02d}分"
    )

    return {
        "time_str": time_str,
        "period": period,
        "period_hint": period_hint,
        "hours_since": hours_since,
        "rel_text": rel_text,
        "avoid_text": avoid,
        "first_time": first_time,
        "is_late_night": period == "深夜",
    }


def build_time_prompt(ctx: dict) -> str:
    lines = [
        "## 当前时间",
        f"{ctx['time_str']}（{ctx['period']}）。",
        ctx["rel_text"],
        "",
        "## 时段语气",
        ctx["period_hint"],
        "",
        "## 时间相关规则（必须遵守）",
        ctx["avoid_text"],
    ]

    if ctx["is_late_night"]:
        lines.append("深夜不要主动开新话题，如果聊得久，可以提醒对方早点睡。")

    if ctx["first_time"]:
        lines.append("这是第一次对话，不要提到过去的任何事。")

    return "\n".join(lines)