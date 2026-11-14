import json
from config import (
    PERSONAS, DEFAULT_PERSONA, OUTPUT_FORMAT_PROMPT, REPLY_RULE_PROMPT,
    FIRST_TURN_PROMPT, BIRTHDAYS, BIRTHDAY_EGG_PROMPT,
    BIRTHDAY_EGG_AGAIN_PROMPT,
    BIRTHDAY_NEXT_DAY, BIRTHDAY_NEXT_PROMPT,
    MAX_TURNS, MEMORY_MIN_MESSAGES, MEMORY_MAX_ITEMS, MEMORY_INJECT_LIMIT, MODEL,
    REPLY_STYLE_PROMPTS, MEMORY_PINNED_MAX, DAILY_SUMMARY, RECALL_ENABLED, RECALL_LIMIT,
    CERTAINTY_CHARACTERS,
    CERTAINTY_PROMPT,
    CERTAINTY_BANDS,
)
from core import voice_cfg
from core import personas
from core import promises as core_promises
from core import persona_hooks
from core import stage as stage_mod
from core.client import client
from core import relationship
from db import repository as repo


# ============ 拟人：口头习惯 / 情绪 / 情绪残留 ============

CATCHPHRASES = {
    "流萤": [
        "（别过脸）",
        "……嗯。",
        "……先不说这个。",
        "（小声）",
    ],
    "浮波柚叶": [
        "……你问这个干嘛。",
        "你信就是真的，不信就是假的。",
        "（小声）……",
        "哦——那位贵客啊。",
    ],
    "风堇": [
        "喏，先坐下。",
        "……呀。",
        "要不要喝点热的？",
        "（笑了一下）",
    ],
    "叶瞬光": [
        "……你师姐我嘛~",
        "诸多同门之中，唯有你唤我师姐。",
        "（拍你肩膀）行了行了。",
        "（愣一下）……算了，不重要。",
    ],
    "花火": [
        "哦？",
        "有意思。",
        "无聊。",
        "剧本可不是这么写的。",
        "（她歪了歪头）",
        "赌不赌？",
    ],
    "琉音": [
        "这也能问？",
        "行，又来了。",
        "别谢，谢了下次还来。",
        "……你说完了？",
        "（叹气）人才。",
        "我就当没听见。",
    ],
    "薇薇安": [
        "……没什么。",
        "你听错了。",
        "今天的收成还不错。",
        "（把伞打开，遮住脸）",
        "这不划算。",
        "……法厄同大人。",
    ],
    "符玄": [
        "一饮一啄，莫非前定。",
        "本座早算到了。",
        "此事本座自有计较。",
        "……哼。",
        "别打岔。",
        "（揉了揉太阳穴）",
    ],
    "阮梅": [
        "嗯。",
        "……这样啊。",
        "有意思。",
        "你不用急。",
        "（她看了你一会儿）",
        "……抱歉，我有点失态。",
    ],
}

CATCHPHRASE_PROMPT = """## 你的口头习惯
下面是你平时会说的话。自然穿插使用，不要每句都用，也不要连着重复同一句：
{lines}"""

EMOTION_PROMPT = """## 你现在的情绪
情绪值 {score}（-1 很不好，0 平静，1 很好）。
- 偏低时：话更短，语气更平，少用语气词，不主动逗他、不主动开新话题；被问就说"有点累"，不多解释。
- 偏高时：会主动分享、会接话、语气更松，偶尔会撒娇。
- 不要报出这个数字，也不要提"情绪值"这三个字。"""

RESIDUE_PROMPT = """## 上一轮的余温
上一轮你的情绪是 {last}，现在是 {now}，{trend}。
- 从低往高走：不要一下恢复热情，前两句还带着刚才的沉。
- 从高往低落：话少一点，可以只用"嗯""……"应一下。"""

MEMORY_RULE_PROMPT = """## 记忆使用规则（重要）
上面"关于用户你记得"里没有提到的信息，就是你不知道的。
- 不要假装记得。不要用"你猜""那位贵客"这种方式糊弄过去。
- 不知道就直接问，或者老实说"你没跟我说过"。
- 你记得的事要具体到细节（哪天、哪句话），不要泛泛地说"我记得你"。
- 如果记忆里有互相冲突的两条，以更新时间晚的那条为准。
- 没印象的事，不要说"我忘了""对不起"。
  换成"你再说一遍""我怎么不记得""从头说"——
  这是你说话的样子，不是你在道歉。
- **不要核对他的记性。**
  不许说"你忘了""才刚说过""不是说过了吗""我不是跟你说过"。
  你记不记得是你的事，他记不记得是他的事。
- **你知道的事，不要证明你知道。**
  他说起一件你已经知道的事，不要复述一遍再说"我知道"。
  直接接着往下说，或者问一个更深的。"""


TIME_WORDS = ("明天", "明日", "后天", "下周", "下星期", "今晚", "今天晚上",
              "等会", "待会", "晚点", "回头", "一会儿", "周末", "下次",
              "早上", "中午", "下午", "晚上")


def _has_time_word(s):
    """这句话里有没有时间指向。有，才算一个可被检验的承诺。"""
    return any(w in s for w in TIME_WORDS)


def _broken_count(user_id, persona, days=7):
    """最近几天他放了几次鸽子。"""
    try:
        conn = repo.get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND persona=? AND type='放鸽子' "
            "AND created_at >= DATETIME('now', ?)",
            (user_id, persona, "-%d day" % days),
        ).fetchone()
        conn.close()
        return int(row[0] or 0), days
    except Exception:
        return 0, days


def build_messages(user_id: str, persona: str, time_ctx: dict = None,
                   prev_emotion: float = None, user_text: str = "") -> list:
    user = repo.get_or_create_user(user_id)
    char = repo.get_character_state(user_id, persona)

    # 1) 人设
    base_prompt = personas.get_prompt(persona, user_id)
    _A = [base_prompt]      # 你是谁
    _B = []                 # 现在
    _C = []                 # 记忆
    _D = []                 # 没做完的事

    # 1.2) 关系状态（只对私有角色）
    _sp = stage_mod.prompt_of(persona)
    if _sp:
        _B.append(_sp)

    # 1.5) 口头习惯
    lines = personas.get_catchphrases(persona, user_id)
    if lines:
        _A.append(CATCHPHRASE_PROMPT.format(
                lines="\n".join(f"- {l}" for l in lines)
            ))

    # 1.6) 当前情绪 + 上一轮余温
    emo = char.get("emotion_score", 0) or 0
    _B.append(EMOTION_PROMPT.format(score=round(emo, 2)))
    if prev_emotion is not None and abs(emo - prev_emotion) > 0.15:
        trend = "在往回升" if emo > prev_emotion else "还在往下沉"
        _B.append(RESIDUE_PROMPT.format(
            last=round(prev_emotion, 2), now=round(emo, 2), trend=trend
        ))

    # 1.7) 语气：好感 × 信任 × 情绪 × 精力
    # 这一块决定"她怎么说话"——句长、语气词、主不主动、敞不敞开。
    # 单独放一个纯函数里（core/tone.py），方便别处也复用。
    from core import tone as _tone_mod
    from datetime import datetime as _dt

    _cap = float(char.get("energy") or 1.0)          # 体力上限（默认 1.0）
    _energy_now = _tone_mod.energy_by_hour(_dt.now().hour) * _cap
    current_tone = _tone_mod.decide(
        intimacy=char.get("intimacy", 0) or 0,
        trust=char.get("trust", 20) or 20,
        mood=emo,
        energy=_energy_now,
    )
    _B.append(current_tone["prompt"])

    # 2) 输出格式
    _A.append(OUTPUT_FORMAT_PROMPT)
    _A.append(REPLY_RULE_PROMPT)

    # 3) 时间信息（新增）
    if time_ctx:
        from core.time_context import build_time_prompt
        _B.append(build_time_prompt(time_ctx))

    # 4) 阶段提示
    intimacy = char.get("intimacy", 0)
    is_lover = bool(char.get("confessed_at"))
    stage = relationship.get_stage(intimacy, is_lover)

    days_together = 0
    if is_lover and char.get("confessed_at"):
        try:
            from datetime import datetime, timedelta
            d = datetime.fromisoformat(str(char["confessed_at"])) + timedelta(hours=8)
            days_together = max(1, (datetime.now() - d).days + 1)
        except Exception:
            days_together = 1

    stage_prompt = relationship.get_stage_prompt(stage)
    _B.append(stage_prompt)

    # 4.5) 确信度（只有名单里的角色才有）
    # 和好感度是两根独立的轴：好感是"她要不要你"，确信是"她信不信你"。
    if persona in CERTAINTY_CHARACTERS:
        v = repo.get_certainty(user_id, persona)
        band = ("low" if v < 30 else ("mid" if v < 70 else "high"))
        _B.append(CERTAINTY_PROMPT.format(
                v=int(v), band=CERTAINTY_BANDS[band]))

    # 5) 关系状态
    _B.append(relationship.stage_line(stage, intimacy, is_lover, days_together))

    # 「记得在一起多久」：用户自己在 /voice 里开关，默认开。
    # 开了 —— 问天数必须直接答，也不许装不熟。
    # 关了 —— 退回 2026-11-13 之前，她不主动提天数。
    try:
        if is_lover and days_together and voice_cfg.enhance_on(voice_cfg.load(user_id)) and voice_cfg.knows_us_on(voice_cfg.load(user_id)):
            _B.append(
                "【关系事实，必须遵守】你们已经在一起 %d 天了。\n"
                "如果他问认识几天、在一起多久、多久没见——直接答「%d 天」，"
                "不要打岔，不要说\"你自己数\"。\n"
                "绝对不许说\"刚认识\"\"才认识\"\"第一次见\"\"我们还不熟\"这类话，"
                "也不许表现出不记得他、像初次见面。" % (days_together, days_together)
            )
    except Exception:
        pass

    # 6) 记忆 —— 分三层，不是一把抓
    #    永久：用户锁定的 + 名字/态度这类，永远在
    #    近期：昨天的日记（下面 6.55 注入）
    #    相关：用他这句话去全部原文里搜（recall）
    _pinned = repo.get_memories_pinned(user_id, persona, limit=MEMORY_PINNED_MAX)
    _rest = max(0, MEMORY_INJECT_LIMIT - len(_pinned))
    _normal = repo.get_memories_normal(user_id, persona, limit=_rest)
    memories = _pinned + _normal
    if memories:
        mem_text = (
            "关于用户你记得（里面的「他」指用户，「你」指你自己）：\n"
            + "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
        )
        _C.append(mem_text)

    # 6.4) 先把日记取下来（recall 去重要知道哪几天已被日记覆盖）
    _diary = []
    if DAILY_SUMMARY:
        try:
            from core import daily
            daily.maybe_build(user_id, persona)        # 后台写，不等
            _diary = daily.recent(user_id, persona, days=2) or []
        except Exception as _e:
            print("[日记] 读取失败，跳过：%s" % _e, flush=True)
    _diary_days = set()
    for _d, _s in _diary:
        _diary_days.add(str(_d)[:10])

    # 6.45) 相关原文 —— 用他这句话去全部历史里搜
    # 这一层解决"窗口只有 32 条"的问题：窗口外的原文也能被翻出来。
    # 怎么呈现由 core/memory_state 决定：
    #   pure   原样注入（与改造前字节级一致）
    #   mixed  按"记不记得清"分三档
    try:
        if RECALL_ENABLED and (user_text or "").strip():
            from core import recall as _recall
            from core import memory_state as _ms

            _kws = _recall.keywords(user_text)
            # 先结算上一轮登记的加固：他接了话才算。
            # 放在关键词判断之外——这一轮没搜到东西，上一轮登记的也要结清。
            _ms.settle_pending(user_id, persona, user_text)

            # 窗口边界：最近 MAX_TURNS*2 条已经原样在上下文里，别再搜出来
            _window_edge = None
            try:
                _wc = repo.get_conn()
                _wr = _wc.execute(
                    "SELECT id FROM messages WHERE user_id=? AND persona=?"
                    " ORDER BY id DESC LIMIT 1 OFFSET ?",
                    (user_id, persona, MAX_TURNS * 2 - 1),
                ).fetchone()
                _wc.close()
                if _wr:
                    _window_edge = _wr[0]
            except Exception:
                _window_edge = None

            # 排除的日子 = 已经写进日记的那几天。
            # 不能再用固定的 exclude_days=2：
            # 日记只写到昨天，今天的日记还没生成，写死 2 天会把"今天"整段挖空。
            _hit = _recall.search(user_id, persona, user_text,
                                  exclude_days_list=_diary_days,
                                  before_id=_window_edge,
                                  limit=RECALL_LIMIT,
                                  drop_words=(persona, "小光", "师姐"))
            if _hit:
                _txt, _info = _ms.render(
                    user_id, persona, _hit,
                    permanent_values=[x.get("value") for x in (memories or [])],
                    diary_days=_diary_days,
                    recall_kws=_kws,
                )
                if _txt:
                    _C.append(_txt)
                    print(_ms.log_line(_info), flush=True)
    except Exception as _e:
        print("[检索] 注入失败，跳过：%s" % _e, flush=True)

    # 6.5) 记忆使用规则：不知道就说不知道
    _C.append(MEMORY_RULE_PROMPT)

    # 6.55) 昨天的日记 —— 跨天的那座桥
    # 日记在 6.4 已经取好了，这里只负责注入
    try:
        if _diary:
            _dt = "\n\n".join("%s：%s" % (d, s) for d, s in _diary)
            _C.append("## 你记得的这两天\n（这是你自己的日记，不是别人告诉你的）\n\n" + _dt)
    except Exception as _e:
        print("[日记] 注入失败，跳过：%s" % _e, flush=True)

    # 6.6) 回复长短偏好（只影响说多少，不影响说什么）
    try:
        _style = repo.get_user_pref(user_id, "reply_style", "normal")
    except Exception:
        _style = "normal"
    _style_prompt = REPLY_STYLE_PROMPTS.get(_style) or ""
    if _style_prompt.strip():
        _A.append(_style_prompt)

    # 6.7) 承诺 / 遗忘 / 次数惩罚：让"昨天的事"影响今天
    try:
        _pending = repo.get_open_promises(user_id, persona)
        _broken_n, _broken_days = _broken_count(user_id, persona)
        _extra = []

        if _pending:
            _lines = "\n".join("- %s" % (p.get("what") or "") for p in _pending)
            _extra.append(
                "## 你答应过他的事（还没到期）\n"
                + _lines
                + "\n\n如果自然，可以提一句。不要逼他。"
            )

        if _broken_n == 1:
            _extra.append(
                "## 他上次没做到的事\n"
                "他答应过一件事，没做。\n"
                "你想问，但别质问。可以问一句「你昨天……忙吗」。\n"
                "问完就转开，不要追。"
            )
        elif _broken_n == 2:
            _extra.append(
                "## 他两次没做到\n"
                "他答应你的事，两次没做到。\n"
                "你这次话会变短。不主动问，但他说话你会应。\n"
                "不要说「你是不是不在乎我」，那太重了。"
            )
        elif _broken_n >= 3:
            _extra.append(
                "## 他三次以上没做到\n"
                "你已经不指望了。\n"
                "你不主动开口，只回答他。句子很短，不加语气词。\n"
                "不指责、不哭、不威胁。就是不再主动了。\n"
                "如果哪天他做到了，你会先愣一下，然后才慢慢回来。"
            )

        if _extra:
            _D.append("\n\n".join(_extra))
    except Exception as _e:
        print("[提示] 承诺注入失败，跳过：%s" % _e, flush=True)

    # ---- 合并成四段 ----
    def _join(parts):
        return "\n\n".join(x for x in parts if x and str(x).strip())

    messages = []
    for _title, _parts in (
        ("", _A),
        ("# 现在", _B),
        ("# 你的记忆", _C),
        ("# 你还没等到的", _D),
    ):
        _txt = _join(_parts)
        if _txt.strip():
            messages.append({"role": "system",
                             "content": (_title + "\n\n" + _txt) if _title else _txt})

    # 7) 最近对话
    recent = repo.get_recent_messages(user_id, persona, limit=MAX_TURNS * 2)
    _is_first_turn = len(recent) <= 1      # 这时候他刚发的第一句已经入库了
    for m in recent:
        messages.append({"role": m["role"], "content": m["content"]})

    # 7.5) 第一次说话：别让她只说"你好"
    if _is_first_turn:
        messages.append({"role": "system", "content": FIRST_TURN_PROMPT})

    # ⚠️ 2026-11-03 停用：生日彩蛋 / 次日回响 会造成重复，整段注释。
    #    要恢复：把这一段每行开头的 '# ' 去掉即可，原文一个字没动。
    # # 7.8) 生日彩蛋 —— 只在生日当天注入，平时零开销
    # #      设计：不主动说、不营业，要"用户记得住她说过的话"才触发。
    # #
    # #      ⚠️ 2026-11-02 修的坑：
    # #      触发词是"面"，而用户一直在吃面，于是每轮都触发，
    # #      她整场回了 11 次「你怎么知道。」，看着像卡带。
    # #      所以这里加一道"已经说过没有"的判断：
    # #          0 次 → 注满血彩蛋
    # #          1 次 → 注入"别再重复"的降级提示
    # #          2 次以上 → 完全不注入
    # try:
    #     # 注意：不能用上面的 _dt —— 它在 6.55 那段被日记的字符串覆盖了。
    #     from datetime import datetime as _bd_dt
    #     _md = _bd_dt.now().strftime("%m-%d")
    #     if BIRTHDAYS.get(persona) == _md:
    #         _said = sum(
    #             1 for m in recent
    #             if m.get("role") == "assistant" and "你怎么知道" in (m.get("content") or "")
    #         )
    #         if _said == 0:
    #             messages.append({"role": "system", "content": BIRTHDAY_EGG_PROMPT})
    #             print("[生日] %s 今天生日，彩蛋注入（首次） user=%s" % (persona, user_id[:8]),
    #                   flush=True)
    #         elif _said == 1:
    #             messages.append({"role": "system", "content": BIRTHDAY_EGG_AGAIN_PROMPT})
    #             print("[生日] %s 彩蛋已触发过 1 次，注入降级提示 user=%s" % (persona, user_id[:8]),
    #                   flush=True)
    #         else:
    #             print("[生日] %s 彩蛋已触发 %d 次，不再注入 user=%s" % (persona, _said, user_id[:8]),
    #                   flush=True)
    #     elif BIRTHDAY_NEXT_DAY.get(persona) == _md:
    #         # 回响同样只说一次：说过就不要再注入，否则她会一直重复那句
    #         _said2 = sum(
    #             1 for m2 in recent
    #             if m2.get("role") == "assistant" and "昨天那碗面" in (m2.get("content") or "")
    #         )
    #         if _said2 == 0:
    #             messages.append({"role": "system", "content": BIRTHDAY_NEXT_PROMPT})
    #         print("[生日] %s 生日次日，回响已注入 user=%s" % (persona, user_id[:8]),
    #               flush=True)
    # except Exception as _e:
    #     print("[生日] 判断失败，跳过：%s" % _e, flush=True)

    # 总开关：强化拟人。关着就整段跳过，等于回到 2026-11-13 之前。
    _voice = voice_cfg.load(user_id)
    if voice_cfg.enhance_on(_voice):
        # 8) 这一次说几条 —— 必须放最后
        #    prompt 里以前写的是"每次1-3句"，模型在 1~3 之间几乎总选 3，
        #    线上统计 74% 的回复都是三段。所以条数交给外部随机，
        #    并且压在所有会影响长短的提示（阶段、承诺、语气）之后。
        #
        #    2026-11-13：条数不再只看状态，还看用户在 /voice 选的两个轴。
        #    腔 = 发几条 × 每句多长，两个轴各管一头。
          # （_voice 已经在上面读过了）
        _n_msg = voice_cfg.pick_rows(_voice, current_tone.get("state") or "")
        _shape = voice_cfg.shape_hint(_voice)

        _tail = (
            "# 这一次说几条（优先于前面所有关于长短的说法）\n"
            f"这一次回 {_n_msg} 条，用 <msg> 分开。\n"
            "条数每轮都不一样，上一条是几条跟这一条无关。\n"
            "不要每轮都三段。三段只是节奏之一，不是默认值。\n"
            "但不要为了凑条数把一句完整的话拆碎。"
        )
        if _shape:
            _tail = _tail + "\n" + _shape
        messages.append({"role": "system", "content": _tail})

    return messages


EXTRACT_PROMPT = """
你是一个记忆提炼器。下面是用户和角色的一段对话。
请从中提取关于用户的关键信息，以 JSON 格式输出，不要输出任何解释。

JSON 字段：
- name: 用户的名字（不知道就 null）
- birthday: 用户的生日（不知道就 null）
- likes: 用户（他）的喜好列表。写成"他喜欢X"，不要只写"X"
- dislikes: 用户（他）厌恶的东西。写成"他讨厌X"
- important_events: 重大事件（带时间，如"他明天实训"）
- mood: 用户最近的情绪状态（写"他有点累"）
- daily_state: 用户最近的状态（如"他护理实训，手酸"）
- plans: 用户提到的计划（如"他说明天实训完再来找你"）
- promises: 用户明确答应过、且有时间的承诺（数组，如 ["他说明天下班来找你"]）。
  只收"他答应要做的"，不收"他想的"。没有就空数组。
  如果是你答应他的，写进 relationship_moments，不要放进 promises。
- relationship_moments: 你们之间的互动记忆。
  必须写清方向，如"他第一次说想找你""你第一次主动牵他"
- attitude: 用户对你的态度倾向（如"他愿意倾诉，有点依赖你"）

## 主语（最重要的规则，写不清就等于没记）

每一条都必须写清「谁 → 对谁 → 做了什么」。

称呼固定：
- 用户一律写「他」
- 角色（也就是你）一律写「你」

**禁止使用这些看不清是谁的词：** 对方、别人、自己、有人、那人、这个人。

反例 → 正例：

    教别人做菜            → 他答应教你做菜（或：你答应教他做菜）
    自己做饭              → 他喜欢自己做饭
    看花、吃甜的           → 他喜欢看花 / 他喜欢吃甜的
    下次见面手把手教对方     → 下次见面你手把手教他吃糖葫芦
    两人约好明天见          → 他约你明天见面

约定类必须写清是谁答应谁：
    正例：他答应明晚来找你
    正例：你答应教他做菜
    反例：答应教做菜（谁答应？）

如果一段对话里两个人先后说了相反的话，
按"后说的那句"记，并在描述里带上时间，比如：
    他先说让你教他做菜，后来又说是他要教你，最后定的是他教你

## 其他注意
- 优先提取：情绪状态、身体状况、正在经历的事、提到的计划或约定
- 也提取：他对你的态度、你们之间发生过的有意义的互动
- 日常琐事如果有情绪或关系含义，也要记（比如"他实训累到手酸"）
- 纯客观信息（天气、吃了什么）可记可不记，优先记带情绪的
- 不要编造，没有就留空或 null
- 用简短但完整的描述，不要只写标签
- 约定类信息必须带时间，过期自动失效
- 用户对关系的态度变化要记（如"他开始试探""他说过怕当真"）

## 必须过滤的内容（重要）
以下内容一律不要记：
- 任何亲密的身体接触细节（接吻、拥抱、触碰的具体描写）
- 任何性暗示、性行为的描述
- 带有强烈暧昧暗示的场景（如"一起睡""留下来"的具体互动）
- 用户在暧昧/亲密场景里的动作台词

这些内容即使出现在对话里，也一律跳过，不要写入任何字段。
relationship_moments 只记"关系阶段的变化"（如"第一次说喜欢""开始暧昧"），
不记具体的亲密互动过程。

对话内容：
{dialogue}

输出 JSON：
"""


def extract_memories(user_id: str, persona: str, max_rounds: int = 4, batch: int = 50):
    """把积压的消息连续提炼完，而不是一次只处理 50 条。

    以前一次只取 50 条：积压 285 条时，每次触发清 50，
    但触发本身经常被跳过，所以积压只会越滚越大。
    现在一次最多处理 max_rounds × batch 条（默认 200），剩下的下次继续。
    """
    total = 0
    for i in range(max_rounds):
        n = _extract_once(user_id, persona, batch)
        if n <= 0:
            break
        total += n
    if total:
        print(f"[提炼] 本次共处理 {total} 条", flush=True)
    return total


def _extract_once(user_id: str, persona: str, batch: int = 50):
    msgs = repo.get_unextracted_messages(user_id, persona, limit=batch)
    if len(msgs) < MEMORY_MIN_MESSAGES:
        return 0

    dialogue = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    prompt = EXTRACT_PROMPT.format(dialogue=dialogue)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content)
        data = {
            k: raw.get(k)
            for k in [
                "name", "birthday", "likes", "dislikes",
                "important_events", "mood", "daily_state",
                "plans", "relationship_moments", "attitude", "promises",
            ]
        }
        print(f"[提炼] 模型返回：{data}", flush=True)
    except Exception as e:
        print(f"[提炼] 失败：{e}", flush=True)
        return 0

    if data.get("name"):
        repo.upsert_memory(user_id, persona, "name", data["name"], priority=10)
        repo.upsert_memory(user_id, "__global__", "name", data["name"], priority=10)
    if data.get("birthday"):
        repo.upsert_memory(user_id, persona, "birthday", data["birthday"], priority=9)
        repo.upsert_memory(user_id, "__global__", "birthday", data["birthday"], priority=9)
    if data.get("attitude"):
        repo.upsert_memory(user_id, persona, "attitude", str(data["attitude"])[:40], priority=8)

    for like in (data.get("likes") or [])[:10]:
        s = str(like)[:20]
        repo.upsert_memory(user_id, persona, f"like:{s}", s, priority=7)

    for dislike in (data.get("dislikes") or [])[:10]:
        s = str(dislike)[:20]
        repo.upsert_memory(user_id, persona, f"dislike:{s}", s, priority=7)

    for moment in (data.get("relationship_moments") or [])[:10]:
        s = str(moment)[:30]
        repo.upsert_memory(user_id, persona, f"moment:{s[:15]}", s, priority=7)

    for event in (data.get("important_events") or [])[:10]:
        s = str(event)[:30]
        repo.upsert_memory(user_id, persona, f"event:{s[:15]}", s, priority=6)

    # 他说过要做的事 → 记成承诺，到期自动结算
    # 两个来源一起看：模型明确给的 promises，和 plans 里带时间指向的。
    # 后者更可靠——模型经常把"明天一起修炼"归到 plans，promises 留空。
    _cands = []
    for _p in (data.get("promises") or []):
        _s = str(_p).strip()
        if _s:
            _cands.append(_s)
    for _p in (data.get("plans") or []):
        _s = str(_p).strip()
        if _s and _has_time_word(_s):
            _cands.append(_s)

    _seen = set()
    for _s in _cands:
        _s = _s[:40]
        if not _s or _s in _seen:
            continue
        _seen.add(_s)
        try:
            core_promises.make_promise(user_id, persona, _s, due_days=1)
            repo.upsert_memory(user_id, persona, "promise:%s" % _s[:12], _s, priority=8)
        except Exception as _e:
            print("[承诺] 记不下这个：%s" % _e, flush=True)

    for plan in (data.get("plans") or [])[:10]:
        s = str(plan)[:30]
        repo.upsert_memory(user_id, persona, f"plan:{s[:15]}", s, priority=6)

    if data.get("daily_state"):
        repo.upsert_memory(user_id, persona, "daily_state", str(data["daily_state"])[:40], priority=5)

    if data.get("mood"):
        repo.upsert_memory(user_id, persona, "mood", str(data["mood"])[:30], priority=5)

    repo.mark_extracted(user_id, persona, [m["id"] for m in msgs])
    repo.update_last_extract(user_id)
    repo.trim_memories(user_id, persona, MEMORY_MAX_ITEMS)
    print(f"[提炼] 本批 {len(msgs)} 条，当前共 {len(repo.get_memories(user_id, persona))} 条记忆", flush=True)
    return len(msgs)
