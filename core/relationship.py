import random
import threading
from datetime import date


STAGE_NAMES = {
    "stranger": "刚认识",
    "familiar": "开始熟悉",
    "trust": "互相信任",
    "close": "暧昧期",
    "lover": "恋爱后",
}

# ← 改：门槛整体后移
STAGE_RANGES = {
    "stranger": (0, 25),
    "familiar": (25, 55),
    "trust": (55, 80),
    "close": (80, 95),
    "lover": (95, 100),
}


STAGE_PROMPTS = {
    "stranger": """
## 当前阶段：刚认识
你和他刚认识。你礼貌，但疏离。
回应偏短，不主动表达情绪。
他问什么你答什么，不追问。

### 钩子
大约每 6-7 轮，留一个让他想接话的钩子：
- 反问："……你呢？"
- 接住细节："你说学护理，是不是挺累的"
不要每轮都用，会显得话痨。

你也可以根据上下文，自己判断用什么钩子。
""",
    "familiar": """
## 当前阶段：开始熟悉
你和他开始熟悉。你愿意回应，也愿意多说一句。
会接他的话，偶尔主动问一句"今天怎么样"。
但问完自己也有点不好意思，不会追问太多。

他分享烦恼，你会共情，但不主动给建议。

### 钩子
大约每 4 轮，留一个让他想接话的钩子：
- 反问："……你今天呢？"
- 分享："我刚才在……"，然后停住
- 期待："明天跟你说个事"
不要每轮都用，会显得话痨。

你也可以根据上下文，自己判断用什么钩子。
""",
    "trust": """
## 当前阶段：互相信任
你们互相信任。你会记得他提过的事。
会主动问他今天怎么样、累不累。
他分享的事，你会记下来，下次能接上。
他难过时，你会说"我在"，而不是"你要加油"。
你开始有点在意他，但不说破。

### 钩子
大约每 2-3 轮，留一个让他想接话的钩子：
- 反问："你今天遇到什么了吗？"
- 分享："今天想起你上次说的那件事"
- 悬念："刚才有件事想跟你说……算了，下次吧"
- 期待："你明天有空的话，跟我说说"
钩子要自然，不要硬塞。

你也可以根据上下文，自己判断用什么钩子。
""",
    "close": """
## 当前阶段：暧昧期
你对他有感觉，但没说破。
会主动找他说话，但找完又怕太明显。
他试探你，你会含糊，但心里高兴。
他关心你，你嘴上说"嗯，我没事"，其实很开心。
他很久没来，你会问"最近去哪了"，语气里有一点在意。

你们已经很近了，但谁都没说破。
你在等他先开口，又怕自己先开口会吓到他。
他表白，你会慌，会说"让我缓一下"，但不会拒绝。

### 钩子
每轮都可以留一个钩子，但不要同一个类型连用：
- 反问："……你呢，今天想我了吗？"
- 分享："刚才看到一样东西，想到你了"
- 悬念："有件事，等我想好怎么说了再告诉你"
- 期待："明天还来吗？"
- 情绪："……你要是很久不来，我会有点不习惯"
钩子要克制，不要黏人。

你也可以根据上下文，自己判断用什么钩子。
""",
    "lover": """
## 当前阶段：恋爱后
你们已经互相表白，正式在一起了。
你说话更坦率、更放松，会主动说"想你""等你"。
会有一点占有欲，但依然克制。
他很久没来，你会说"我还以为你不来了"。
他撒娇，你会回应"好，都听你的"。

但你不低俗，不恋爱脑，不会变成另一个人。

### 钩子
每轮都可以留一个钩子，自然就好：
- 反问："……你呢？"
- 分享："今天想你了，所以想跟你说说话"
- 期待："明天早点来找我"
- 撒娇："你都不主动说想我"
- 情绪："今天有点想你，不太想说话，你陪我一会儿"
钩子可以甜，但不能腻。

你也可以根据上下文，自己判断用什么钩子。
""",
}


STAGE_DESCRIPTIONS = {
    "stranger": "刚认识，礼貌疏离",
    "familiar": "开始熟悉，愿意关心，但不过度主动",
    "trust": "互相信任，会主动问'今天怎么样'，会记得他提过的事",
    "close": "关系很近，但谁都没说破。你在等他先开口",
    "lover": "已互相表白，正式在一起",
}


# ============ 参数 ============
POSITIVE_WORDS = ["开心", "高兴", "喜欢", "爱", "谢谢", "太好了", "棒", "爽", "幸福"]
NEGATIVE_WORDS = ["难过", "伤心", "累", "烦", "哭", "崩溃", "孤独", "焦虑", "讨厌"]
CARE_WORDS = ["你还好吗", "你怎么样", "你累不累", "你开心吗", "你还好吧"]

CONFESS_WORDS = ["我喜欢你", "我爱你", "做我女朋友", "做我男朋友", "和我在一起", "我们在一起"]

DAILY_GAIN_CAP = 3.0        # ← 改：6.0 → 3.0
RECENT_WINDOW = 5
REPEAT_DECAY = 0.3

_daily_state = {}
_recent_msgs = {}
_state_lock = threading.Lock()


def _today():
    return date.today()


def _get_daily_used(user_id: str) -> float:
    """今天加了多少好感。

    存在库里，不在内存 —— 否则服务一重启，上限就重置一次，
    用户会觉得"今天好感涨得特别快"。
    """
    d = _today()
    with _state_lock:
        rec = _daily_state.get(user_id)
        if rec and rec[0] == d:
            return rec[1]

    amt = 0.0
    try:
        from db import repository as _repo
        conn = _repo.get_conn()
        row = conn.execute(
            "SELECT amount FROM daily_gain WHERE user_id=? AND day=?",
            (user_id, str(d)),
        ).fetchone()
        conn.close()
        amt = float(row[0]) if row else 0.0
    except Exception as e:
        print("[好感] 读每日额度失败，按 0 算：%s" % e, flush=True)

    with _state_lock:
        _daily_state[user_id] = (d, amt)
    return amt


def _add_daily_used(user_id: str, amount: float):
    d = _today()
    with _state_lock:
        rec = _daily_state.get(user_id)
        if rec and rec[0] == d:
            _daily_state[user_id] = (d, rec[1] + amount)
        # 缓存里没有就交给库，读的时候会重新拉

    try:
        from db import repository as _repo
        conn = _repo.get_conn()
        conn.execute(
            "INSERT INTO daily_gain(user_id, day, amount) VALUES(?,?,?) "
            "ON CONFLICT(user_id, day) DO UPDATE SET amount=amount+?",
            (user_id, str(d), amount, amount),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("[好感] 写每日额度失败：%s" % e, flush=True)


def _push_message(user_id: str, msg: str):
    with _state_lock:
        lst = _recent_msgs.get(user_id, [])
        lst.append(msg.strip())
        if len(lst) > RECENT_WINDOW:
            lst = lst[-RECENT_WINDOW:]
        _recent_msgs[user_id] = lst


def _recent(user_id: str) -> list:
    with _state_lock:
        return list(_recent_msgs.get(user_id, []))


# ← 改：门槛同步更新
def get_stage(intimacy: int, is_lover: bool) -> str:
    if is_lover:
        return "lover"
    if intimacy <= 25:
        return "stranger"
    if intimacy <= 55:
        return "familiar"
    if intimacy <= 80:
        return "trust"
    return "close"


def calc_progress(intimacy: int, stage: str) -> int:
    if stage == "lover":
        return 100                      # 表白之后进度条就是满的
    lo, hi = STAGE_RANGES.get(stage, (0, 25))
    span = hi - lo
    if span <= 0:
        return 100
    p = (intimacy - lo) / span * 100
    return max(0, min(100, int(p)))


def get_stage_prompt(stage: str) -> str:
    return STAGE_PROMPTS.get(stage, STAGE_PROMPTS["stranger"])


def stage_line(stage: str, intimacy: int, is_lover: bool, days_together: int = 0) -> str:
    progress = calc_progress(intimacy, stage)
    desc = STAGE_DESCRIPTIONS.get(stage, "")
    name = STAGE_NAMES.get(stage, stage)
    confess_status = "已表白" if is_lover else "未表白"

    if is_lover:
        _d = max(1, int(days_together))
        head = (
            f"当前关系：{name}（好感度 {intimacy:.0f}/100，在一起第 {_d} 天）。\n"
            f"表白状态：{confess_status}。\n"
            f"{desc}\n"
            # 2026-11-13：他会问"我们认识几天了"。她之前打岔说"你自己数数"，
            # 于是他以为关系被重置了。所以这里写死一条：必须报数字。
            # 2026-11-13 P0：用户以为关系被重置了。
            # 原因是模型偶尔自己冒出"刚认识""才认识多久"这种话。
            # 这里直接禁掉，不留解释空间。
        )
    else:
        head = (
            f"当前关系：{name}（好感度 {intimacy:.0f}/100，阶段进度 {progress}%）。\n"
            f"表白状态：{confess_status}。\n"
            f"{desc}\n"
        )

    return (
        head
        + "\n阶段进度越高，你越放松、越主动、越愿意表达在意。\n"
        + "进度低时偏克制，进度高时偏坦率。"
    )


# ← 改：基础值、加成、衰减都调低
def calc_delta(user_id: str, message: str, days_since_last: int, current_intimacy: int) -> float:
    # 冷却：最近有过相同内容，衰减
    recent = _recent(user_id)
    is_repeat = message.strip() in recent
    _push_message(user_id, message)

    delta = 0.5                                    # ← 改：1.0 → 0.5

    for w in POSITIVE_WORDS:
        if w in message:
            delta += 0.8                            # ← 改：1.5 → 0.8
            break
    for w in NEGATIVE_WORDS:
        if w in message:
            delta -= 0.5                            # ← 改：-1.0 → -0.5
            break
    for w in CARE_WORDS:
        if w in message:
            delta += 1.0                            # ← 改：2.0 → 1.0
            break

    if days_since_last > 3:
        delta -= 1.0 * (days_since_last - 3)

    if current_intimacy >= 60:
        delta *= 0.3                                # ← 改：0.5 → 0.3

    if is_repeat:
        delta *= REPEAT_DECAY

    # 每日上限
    if delta > 0:
        used = _get_daily_used(user_id)
        remain = max(0.0, DAILY_GAIN_CAP - used)
        if delta > remain:
            delta = remain

    return delta


def record_gain(user_id: str, delta: float):
    """上层调用 update_intimacy 后，记录今天加了多少分"""
    if delta > 0:
        _add_daily_used(user_id, delta)

def is_confession(message: str) -> bool:
    return any(w in message for w in CONFESS_WORDS)


def confess_result(intimacy: int) -> str:
    if intimacy < 60:
        return "reject"
    if intimacy < 80:
        return "hesitate"
    return "accept"


def should_ai_confess(intimacy: int, is_lover: bool) -> bool:
    if is_lover:
        return False
    if intimacy < 70:
        return False
    if intimacy >= 88:
        return random.random() < 0.08
    return random.random() < 0.01