import time
import random
import re
import threading
from datetime import datetime

from config import (
    MEMORY_EVERY_N_TURNS,
    SLEEP_APPROACH_MINUTES,
    SLEEP_APPROACH_PROMPT,
    MINOR_WEEKLY_QUOTA,
    MINOR_PROMPT,
    QUENCH_ENABLED,
)
from core import client, memory, certainty, stage, promises, relationship, milestones, permissions
from core import mode as mode_mod
from core import deai
from core import voice_cfg
from core.guard import guard
from core.emotion import update_emotion
from core import sleep as sleep_mod
from core.sleep import is_sleep_time, minutes_until_sleep
from db import repository as repo
from services import billing


CONFESS_PROMPTS = {
    "reject": (
        "他正在向你表白。你们关系还不够深。"
        "你婉拒，说'还没准备好'，但不冷漠，留一点余地。"
    ),
    "hesitate": (
        "他正在向你表白。你对他有好感，但还没准备好。"
        "别一句话答完。先停一下，说'让我缓一下，好吗'，"
        "再补一句'不是不愿意'，留一个'再靠近一点'的信号。"
    ),
    "accept": (
        "他正在向你表白。你也喜欢他。"
        "别一句'嗯，我愿意'就完事。"
        "先顿一下，然后说'我一直在等你说这句'，或者'……你终于说了'。"
        "再补一句克制的坦白，比如'我也是'。"
    ),
}

AI_CONFESS_PROMPT = """
现在触发表白场景。你们关系已经足够亲近，你决定主动开口。
不要一句话说完，是一次完整的对话：
1. 先犹豫，说"我有件事想和你说……但不知道怎么说"
2. 停顿一下，然后开口
3. 说出那句关键的话（含蓄或直接，看你的性格）
4. 等待他回应，不要自问自答。
"""


# /voice 里「说人话」的开关，当前请求设置的值。
# 用模块级变量是因为 clean_output 是流式的回调，签名不能随便加参数。
_PLAIN_ON = [True]


def clean_output(text: str) -> str:
    # 模型有时会写成 <msg>…</msg>（带闭合标签）。分隔符 <msg> 要留着给
    # split_chunks 用，只清掉闭合的 </msg>，否则它会原样显示在聊天里。
    text = re.sub(r"</msg>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    # 模型经常以 <msg> 开头。流式阶段空段会被丢掉，不会多发气泡，
    # 但入库的原文会以 <msg> 打头，重放历史时会多出一个空段。
    while text.startswith("<msg>"):
        text = text[5:].strip()
    # 淬：去掉 AI 味（动作描写、书面词）。
    # 流式片段上只做安全的局部替换，结构类规则留给整条消息。
    if QUENCH_ENABLED and _PLAIN_ON[0]:
        text = deai.quench_segment(text)
    return text


# 只认真正的句末。不要把「…」「～」算进来——模型常连写"……"，
# 按字符切会切出一个个只含标点的气泡。
_END_CHARS = "。！？\n"
_SOFT_CHARS = "，、；："


def _has_word(s: str) -> bool:
    """这一段里有没有实字。只有标点的段不该单独发出去。"""
    for ch in s:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _cut_point(buf: str) -> int:
    """流式输出时，判断缓冲区里"从哪切一刀"（cut 之前的部分可以发了）。

    返回 -1 表示还不够，继续攒。
    优先切在句末，攒到 60 字还没句号就退而求其次切在逗号处。
    """
    for i, ch in enumerate(buf):
        if ch in _END_CHARS and i >= 2:
            return i + 1
        if i >= 60:
            for j in range(i, 20, -1):
                if buf[j] in _SOFT_CHARS:
                    return j + 1
            return i + 1
    return -1


def split_chunks(text: str, max_chunks: int = 4, merge: bool = True) -> list:
    parts = re.split(r"\s*</?msg>\s*", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return [text]
    if len(parts) > max_chunks:
        parts = parts[:max_chunks - 1] + [" ".join(parts[max_chunks - 1:])]

    # 节奏随机化：真人不会每条都一样长，偶尔把相邻的短句并成一条
    if merge and len(parts) > 1:
        merged = [parts[0]]
        for p in parts[1:]:
            if len(p) <= 6 and len(merged[-1]) <= 18 and random.random() < 0.45:
                merged[-1] = merged[-1] + p
            else:
                merged.append(p)
        parts = merged

    return parts


def calc_delay(chunk: str) -> float:
    hour = datetime.now().hour
    if hour >= 23 or hour < 7:
        slow = 1.8          # 深夜打字更慢
    elif 7 <= hour < 10:
        slow = 1.3
    else:
        slow = 1.0

    base = min(5.0, 1.0 + len(chunk) * 0.08) * slow
    delay = base + random.uniform(0.3, 1.0)

    if len(chunk) > 12 and random.random() < 0.05:   # 只在说长句时"走开"一下
        delay += random.uniform(3.0, 7.0)

    return delay


def _days_since(ts) -> int:
    """距离上次对话过了几天。ts 为空返回 0。"""
    if not ts:
        return 0
    try:
        return max(0, (datetime.now() - datetime.fromisoformat(str(ts))).days)
    except Exception:
        return 0


def handle_message(user_id: str, session_id: str, message, persona: str):
    """message 可以是字符串，也可以是列表（同一轮连发的几条）。

    多条时：每条单独入库（刷新后仍是一个个独立气泡），
    但拼成一段喂给模型，只生成一次回复。
    """
    if isinstance(message, str):
        msgs = [message]
    else:
        msgs = [m for m in message if str(m).strip()]
    if not msgs:
        return
    combined = "\n".join(msgs)

    # ===== 权限：被停用的账号不回复 =====
    # 只拦 banned，普通用户的功能保持完整（原则：用额度控成本，不用权限锁功能）
    user = repo.get_or_create_user(user_id)
    if not permissions.can_chat(user):
        yield "（她看了你一眼，没有开口）", ""
        return

    # ===== 免打扰时段 =====
    # 以前是「只存消息、完全不理」，用户会觉得被无视。
    # 现在改成照样回复，但用"被吵醒"的语气，一两句就结束。
    # 注意：用户没设免打扰时，这里什么都不做。
    quiet_now = sleep_mod.in_quiet_hours(user)

    action, payload = guard.check_input(combined)
    if action == "block":
        yield payload, ""
        return

    # ===== 额度 =====
    # 未成年：走每周固定条数，不扣钱（余额那套对他们不适用）。
    # 成年：走余额。
    quota = repo.check_quota(user_id, MINOR_WEEKLY_QUOTA, need=max(1, len(msgs)))
    if quota["minor"]:
        if not quota["allowed"]:
            yield ("这周先到这儿了。\n\n下周再来，我还在这儿。", "")
            return
    elif not billing.has_balance(user_id):
        # 对"来说话的人"，这句比"充值后再来"重要得多：
        # 不催钱、不消失，而且给一个"我记住了"的交代。
        yield ("⚠️ 余额不够发下一条了。\n\n"
               "刚才那些，我都记住了。", "")
        return

    # 先取"上一次和这个角色说话"的时间，再存本条（否则会取到刚存的这条）
    last_active_at = repo.get_last_active_by_persona(user_id, persona)

    for m in msgs:
        repo.save_message(session_id, user_id, persona, "user", m)

    char = repo.get_character_state(user_id, persona)
    prev_emotion = char.get("emotion_score", 0) or 0

    from core import time_context
    time_ctx = time_context.get_time_context(last_active_at)

    days_since = _days_since(last_active_at)
    in_companion = mode_mod.is_companion(user_id)

    # 陪伴模式：不涨好感度，也不记增长曲线。其余（情绪、活跃时间）照旧。
    if not in_companion:
        current_intimacy = char.get("intimacy", 0)
        delta = relationship.calc_delta(user_id, combined, days_since, current_intimacy)
        repo.update_character_intimacy(user_id, persona, delta)
        relationship.record_gain(user_id, delta)
    repo.update_last_active(user_id)

    new_emotion = update_emotion(prev_emotion, combined)
    repo.update_character_emotion(user_id, persona, new_emotion)

    # 信任：涨得比好感慢，而且不看单条消息说得多甜。
    # 每轮固定 +0.3，聊一百轮才到 50 —— 它是"处出来的"，不是"哄出来的"。
    # 以后有事件机制了（吵架、坦白、放鸽子），再按事件加减。
    repo.update_character_trust(user_id, persona, 0.3)

    char = repo.get_character_state(user_id, persona)
    intimacy = char.get("intimacy", 0)
    is_lover = bool(char.get("confessed_at"))
    extra_prompt = None

    if in_companion:
        # 陪伴模式：不判表白、不推进关系、不发恋爱提示
        extra_prompt = None
    elif relationship.is_confession(combined) and not is_lover:
        result = relationship.confess_result(intimacy)
        extra_prompt = CONFESS_PROMPTS[result]
        if result == "accept":
            repo.set_character_confessed(user_id, persona)
            print(f"[表白] 用户主动表白，accept，进入 lover", flush=True)
    elif (not is_lover) and relationship.should_ai_confess(intimacy, is_lover):
        extra_prompt = AI_CONFESS_PROMPT
        repo.set_character_confessed(user_id, persona)
        print(f"[表白] AI 主动表白，intimacy={intimacy}，进入 lover", flush=True)

    # 纪念：只记录"刚刚发生"的第一次。不弹窗、不算分，只在下面注入一句提示
    new_milestones = milestones.check_and_unlock(user_id, persona)

    # 关系状态：只有私有角色会走，其他角色零开销
    if not in_companion:
        try:
            stage.advance(user_id, persona, combined)
        except Exception as _e:
            print(f"[状态] 推进失败，跳过：{_e}", flush=True)

    # 承诺：到期了没兑现？现在结算
    try:
        promises.settle_due(user_id, persona)
    except Exception as _e:
        print(f"[承诺] 结算失败，跳过：{_e}", flush=True)

    # 确信度：只有名单里的角色才有这条线，其他角色这里零开销
    try:
        certainty.apply(user_id, persona, combined)
    except Exception as _e:
        print(f"[确信度] 更新失败，跳过：{_e}", flush=True)

    messages = memory.build_messages(user_id, persona, time_ctx,
                                     prev_emotion=prev_emotion,
                                     user_text=combined)
    ms_prompt = milestones.build_prompt(new_milestones)
    if ms_prompt:
        messages.append({"role": "system", "content": ms_prompt})

    # ===== 彩蛋：小暖 =====
    # 只触发一次。用 hidden: 前缀存标记，纪念页会过滤掉，不会多出一张卡片。
    if "小暖" in combined and not repo.has_milestone(user_id, persona, "hidden:xiaonuan"):
        messages.append({"role": "system", "content": guard.XIAO_NUAN_PROMPT})
        repo.add_milestone(user_id, persona, "hidden:xiaonuan", "——")

    if action in ("steer", "care"):
        messages.append({"role": "system", "content": payload})
    if extra_prompt:
        messages.append({"role": "system", "content": extra_prompt})

    # 临近睡眠：注入引导提示
    mins_left = minutes_until_sleep()
    if 0 <= mins_left <= SLEEP_APPROACH_MINUTES:
        approach = SLEEP_APPROACH_PROMPT.format(
            time_str=datetime.now().strftime("%H:%M"),
            minutes=mins_left,
        )
        messages.append({"role": "system", "content": approach})
        print(f"[临近休息] 距入睡 {mins_left} 分钟，注入引导", flush=True)

    # 用户设的免打扰时段（放在最后，优先级最高——覆盖上面所有语气设定）
    if quiet_now:
        messages.append({"role": "system", "content": sleep_mod.quiet_prompt()})
        print(f"[免打扰] user={user_id[:8]} 在免打扰时段，用被吵醒的语气回复", flush=True)

    # 未成年：锁死恋爱线（放在最后，优先级最高）
    if quota["minor"]:
        messages.append({"role": "system", "content": MINOR_PROMPT})
        print(f"[未成年] user={user_id[:8]} 本周 {quota['used']}/{quota['limit']}，锁恋爱线", flush=True)

    partial = ""      # 完整原文（含 <msg>，要入库）
    usage = None
    buffer = ""       # 待发送的缓冲（已去掉分隔标签）
    blocked = False

    # 她说话的样子：用户在 /voice 里调的东西，这一次就用上
    _voice = voice_cfg.load(user_id)
    _temp = voice_cfg.temp_of(_voice)
    _cap = voice_cfg.cap_of(_voice)
    _freq, _pres = voice_cfg.penalties_of(_voice)
    _PLAIN_ON[0] = voice_cfg.plain_on(_voice)

    try:
        for delta_text, u in client.stream_chat(
                messages,
                temperature=_temp,
                max_tokens=_cap,
                frequency_penalty=_freq,
                presence_penalty=_pres):
            if u:
                usage = u
            if not delta_text:
                continue

            partial += delta_text
            # partial 保留原文（load_history 靠 <msg> 还原分段）
            # buffer 保留 <msg> —— 它是模型自己划的消息边界，必须当分段依据
            buffer += delta_text.replace("</msg>", "")

            # 敏感词：边流边查。命中时这一段还没发出去，来得及拦
            ok_now, _ = guard.check_output(partial)
            if not ok_now:
                blocked = True
                break

            # ① 先按 <msg> 切：模型说这里该断一条，就断一条
            while True:
                idx = buffer.find("<msg>")
                if idx < 0:
                    break
                seg = clean_output(buffer[:idx])
                buffer = buffer[idx + 5:]
                if seg:
                    yield seg, ""

            # ② 再按句末切：长句不用等整段生成完
            while True:
                cut = _cut_point(buffer)
                if cut < 0:
                    break
                seg = clean_output(buffer[:cut])
                buffer = buffer[cut:]
                seg = re.sub(r"</?msg>", "", seg).strip()
                if not seg:
                    continue
                if not _has_word(seg):
                    # 只有标点（比如单独的"……"），塞回去跟下一段一起发
                    buffer = seg + buffer
                    break
                if guard.check_harm(seg):
                    print(f"[反伤害] 流式命中，替换一段", flush=True)
                    seg = "……刚才那句不算。"
                yield seg, ""

    except Exception as e:
        # 不暴露原始错误，用角色的语气兜底
        print(f"[生成失败] {type(e).__name__}: {e}", flush=True)
        if action == "care":
            yield guard.SELF_HARM_FALLBACK, ""
        else:
            yield "……等我一下。我这边好像卡住了，再试一次好吗？", ""
        return

    if blocked:
        yield "⚠️ 这个话题我不太方便继续聊，我们换个轻松点的吧～", ""
        return

    # 收尾：把最后没发完的那点尾巴发出去（顺便去掉可能残留的半个标签）
    tail = re.sub(r"<[a-zA-Z/]{0,5}$", "", buffer)
    tail = clean_output(tail)
    if tail and not _has_word(tail):
        tail = ""
    if tail:
        if guard.check_harm(tail):
            tail = "……刚才那句不算。"
        yield tail, ""

    partial = clean_output(partial)
    print(f"[原始回复] {repr(partial)}", flush=True)

    completion_tokens = usage.completion_tokens if usage else 0
    repo.save_message(session_id, user_id, persona, "assistant", partial, completion_tokens)

    if usage:
        # 未成年不扣钱，只记 token 统计
        if not quota["minor"]:
            billing.charge(user_id, usage.prompt_tokens, usage.completion_tokens)
        repo.add_tokens(user_id, usage.total_tokens)

    # 未成年：用掉本周配额（按她这次发了几条算）
    if quota["minor"]:
        repo.consume_quota(user_id, max(1, len(msgs)))

    # 提炼触发：看「这个角色积压了多少条」，不看总消息数。
    # 旧写法是 total_msgs % 30 == 0 —— 但每轮加的消息数不固定（防抖会合并多条），
    # 经常直接跳过 30 这个点，那一次触发就永久丢了，于是长期不提炼。
    pending = repo.count_unextracted(user_id, persona)
    if pending >= MEMORY_EVERY_N_TURNS * 2:
        # 提炼丢到后台，别让这一轮回复多等 5-15 秒
        threading.Thread(
            target=memory.extract_memories,
            args=(user_id, persona),
            daemon=True,
        ).start()
        print(f"[提炼] 积压 {pending} 条，已丢到后台线程", flush=True)




