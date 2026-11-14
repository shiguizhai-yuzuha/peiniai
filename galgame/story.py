# -*- coding: utf-8 -*-
"""两轮循环生成"出去玩"的剧情。

外层：一天一个大纲（去哪、发生什么、留什么线索）
内层：每一幕的台词和选择

输出一份 story.json。render.py 负责把它变成 .rpy。

用法：
    python generator/story.py --city 杭州 --days 3 --scenes 2 --out runs/story_hz.json
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 角色设定。以后从配置读。
CHARACTERS = {
    "浮波柚叶": """浮波柚叶，二十出头，在城里开一家小古董店（释诡斋）。
性格：
- 说话短，爱用反问，不解释自己
- 爱编怪谈吓人，讲着讲着自己会当真，讲到一半会停下来
- 嘴硬心软：嘴上说"随便你"，然后默默跟着；关心都藏在细节里，从不说肉麻话
- 被戳到的时候会岔开话题，或者只回一个"……"
说话方式：
- 短句，一句一行，不用书面语
- 不撒娇，不喊"哥哥"
- 会突然安静""",
}

# 杭州的真实地点。不许写"街道""湖边"。
HANGZHOU = [
    "杭州东站", "断桥", "白堤", "河坊街", "南宋御街", "灵隐寺",
    "龙井村", "九溪十八涧", "小河直街", "湖滨银泰", "雷峰塔", "苏堤",
]

VALID_BG = ["black", "bg_station", "bg_street", "bg_lake", "bg_room", "bg_night"]

# 一趟旅行的七段。中间是"玩"。
ROLE_HINT = {
    "邀约": ("她开口约你" if True else ""),   # 实际文案在下面按好感分
    "来": "你从出发地出发。路上、等车、看窗外。到了以后碰头。",
    "玩": "一起去了一个地方，发生了那件计划外的事。",
    "返程": "收拾东西，去车站。路上两个人都有点不想说话。",
    "送别": "站台。不是'她走了'，是一件小事没做完（伞没修好/奶茶没喝完/话没说完）。",
}


def day_roles(days: int):
    """给每一天分配阶段。天数少的时候中间省掉。"""
    out = []
    for d in range(1, days + 1):
        if d == 1:
            r = "邀约"
        elif d == 2:
            r = "来"
        elif d == days and days >= 3:
            r = "送别"
        elif d == days - 1 and days >= 5:
            r = "返程"
        else:
            r = "玩"
        out.append((d, r))
    return out


DEFAULT_PROFILE = {
    "name": "",
    "likes": [],
    "dislikes": [],
    "state": "",
    "mood": "",
    "attitude": "",
    "intimacy": 30,
    "trust": 50,
}


# ============ 外层：一天的大纲 ============

DAY_PROMPT = """你是视觉小说编剧。现在只写{total}天里的**第 {day} 天**的大纲。

【角色】
{character}

【用户】
名字：{user_name}（只供你心里知道，写进旁白和事实时一律用「你」）
喜欢：{user_likes}
现在状态：{user_state}
情绪：{user_mood}
对你的态度：{user_attitude}

【关系】
好感 {intimacy}/100，信任 {trust}/100
（好感低 → 她保持距离；好感高 → 她会有不自觉靠近的瞬间）

【出发地】{origin}
【目的地】{city}
【可用地点】{places}

【这是一趟旅行】
第 1 天是"邀约"，第 2 天是"来"（从出发地出发），中间是"玩"，
倒数第二天是"返程"，最后一天是"送别"。
同一个人、同一座城，但这几天是"一趟"。

【今天这一段是什么】
{role}：{role_hint}

【前面发生了什么（摘要，从早到晚）】
{summary}

【已经确立的事实（不能改，不能忘）】
{facts}

【还没收的线索（第几天开的）】
{threads}

【这一天该完成的】
{role_hint}

【硬性要求】
1. 必须点出至少 2 个真实的{city}地点名，不许写"街道""湖边""某个地方"
2. 三天里必须有一天出现一件"计划外的事"（下雨/迷路/打不开门/吃到难吃的东西/末班车走了）
   今天是第 {day} 天，{unplanned_hint}
3. 必须有一处尴尬：两个人有三十秒不知道说什么
4. 必须有一个具体物件（一杯奶茶/一张票根/一把坏掉的伞），后面几天要还在
5. 这一天结束的时候，有什么东西和开始时不一样了
5.5 按阶段：
    「邀约」——这一段不在目的地。是出发前。电话/消息/她店里。
             出发地是「{origin}」，要提到"过去要多久"
             （如果出发地是新艾利都，那是虚构城市，别写真实高铁车次）
    「来」——  路上。车站、车厢、看窗外、到站。
             这一段的重点是"她在等你"或"你还没见到她"
    「返程」——回去的路上。两个人都知道快分开了，但谁都不说
    「送别」——站台。不许写"她走了"，要写"有件事没做完"
6. **上面"已经确立的事实"一个字都不能改。** 伞第 1 天断了，第 5 天还是断的
7. facts_new 只写"能验证的事实"，不写情绪（❌"她有点心动" ✅"她把伞塞给他了"）

【只输出 JSON】
{{
  "day": {day},
  "role": "{role}",
  "title": "两个字的小标题",
  "places": ["今天去的真实地点，2-3 个"],
  "outline": "这一天大致怎么过，80 字以内",
  "unplanned": "那件计划外的事，一句话",
  "awkward": "那处尴尬，一句话",
  "object": "那个具体物件，一句话",
  "change": "这一天结束时的变化，一句话",
  "threads_out": ["这一天结束后还没收的线索，1-3 条"],
  "beats": ["每一幕结束时「什么变了」，一共 {scenes} 条。必须递进：第 2 条从第 1 条结束的地方开始，第 3 条从第 2 条结束的地方开始。两条不许说同一件事。每条 20 字以内"],
  "threads_closed": ["这一天收掉的线索（从上面那份里挑），没有就空数组"],
  "facts_new": ["这一天新确立的事实，1-3 条。要具体：'伞骨断了'，不是'气氛变好了'。写事实时用「你」指代用户，不许写他的名字"],
  "summary": "这一天的摘要，一句话，30 字以内"
}}

只输出 JSON。"""


# ============ 内层：一幕的台词 ============

SCENE_PROMPT = """你是视觉小说编剧。现在只写**第 {day} 天 · 第 {scene} 幕**。

【角色】
{character}

【这一天的大纲】
{day_json}

【已经确立的事实（不能矛盾）】
{facts}

【用户】
名字：{user_name}（只供你心里知道，写进旁白和事实时一律用「你」）
喜欢：{user_likes}
现在状态：{user_state}

【关系】
好感 {intimacy}/100

【上一幕结束在】
{previous}

【今天前面几幕已经写过这些了 —— 一个字都不许重演】
{written}

【这一幕要完成的事（只写这一件）】
{beat}

【这一幕】
背景：{bg}
要写 {n_lines} 条 lines
{scene_hint}

【硬性要求】
0. **旁白一律用第二人称"你"，绝不用"我"，也绝不写用户的名字。**
   ✅"你推开门"　❌"我推开门"　❌"刘了凡推开门"
   用户在本子里只有一种叫法：你。
1. 旁白写"事实"，不写"氛围"。❌"风带着雨的味道" ✅"雨下起来了，伞只有一把，她半边肩膀湿了"
2. 台词短，一句一行，不用书面语。**她说出来的每一句，必须像她本人**——句子长短、语气词、口癖都要对，不要写成"温柔的女主角"那种通用腔。如果人设里写了她爱说什么、不爱说什么，照那个来
3. 不要总结、不要抒情、不要写"他们相视一笑"
3.4 **上面「已经确立的事实」是铁律。**
   如果它说"伞给了他"，那这一幕伞就在他手上，她不能说"我带走"。
   如果事实和你想写的有冲突，以事实为准，改你的写法。
3.5 **前面几幕写过的东西，这一幕不能再写一遍。**
   尤其是：她已经问过的问题、已经递过的东西、已经断掉的伞骨。
   这一幕要往前推，不是重演。
4. 如果这一幕有选择点，给 2 个选项
5. bg 只能从这些里选：{bgs}
6. 每条 line 的 who 只能是 "" 或 "{char_name}"
{branch_hint}

【只输出 JSON】
{{
  "id": "d{day}s{scene}",
  "bg": "{bg}",
  "lines": [
    {{"who": "", "bg": "{bg}", "text": "旁白，第二人称"}},
    {{"who": "{char_name}", "text": "台词"}}
  ],
  "choices": [
    {{"text": "选项文字", "affection": 2, "trust": 1, "reply": "她的一句反应", "next": "d{day}s{next_scene}"}},
    {{"text": "另一个选项", "affection": 1, "reply": "反应", "next": "d{day}s{next_scene}"}}
  ],
  "end": "这一幕的收尾旁白，一句"
}}

choices 没有选择点就写空数组 []。
只输出 JSON。"""


def _client():
    from openai import OpenAI

    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        env = r"D:\Python学习\演示\.env"
        if os.path.exists(env):
            with open(env, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("DEEPSEEK_API_KEY"):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("找不到 DEEPSEEK_API_KEY")
    return OpenAI(api_key=key, base_url="https://api.deepseek.com")


def _call(cli, model, prompt, max_tokens=2600, retries=2):
    """调模型。三道保险：重试、超时、截断检测。

    为什么必须重试：一部剧 28 次调用，不重试的话失败率是 40% 以上。
    """
    import time as _t

    last = None
    for attempt in range(retries + 1):
        try:
            r = cli.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                max_tokens=max_tokens,
                timeout=120,
                response_format={"type": "json_object"},
            )
            ch = r.choices[0]
            # 截断检测：宁可重试，也不要一个少了两句的 JSON
            if getattr(ch, "finish_reason", "") == "length":
                raise RuntimeError("被截断（finish_reason=length）")

            raw = ch.message.content or ""
            tok = r.usage.total_tokens if r.usage else 0
            if not raw.strip():
                raise RuntimeError("返回空")
            return raw, tok
        except Exception as e:
            last = e
            if attempt < retries:
                wait = 2 if attempt == 0 else 5
                print("      [重试 %d/%d] %s，等 %ds"
                      % (attempt + 1, retries, str(e)[:60], wait), flush=True)
                _t.sleep(wait)

    raise RuntimeError("三次都失败：%s" % str(last)[:80])


def _parse(raw):
    t = (raw or "").strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("没找到 JSON")
    return json.loads(t[i:j + 1])


# ============ 组装 ============

def generate_day(cli, model, character, profile, city, day, total,
                 bible, places, unplanned_today, role="玩", origin="新艾利都",
                 scenes_per_day=3):
    _scenes_per_day = scenes_per_day
    role_hint = ROLE_HINT.get(role, ROLE_HINT["玩"])
    if role == "邀约":
        if int(profile.get("intimacy", 30)) >= 60:
            role_hint = ("她开口约你。说得随意，但她准备过。"
                         "比如「我这周有空。你要不要来」，说完立刻补一句「不来也行」。")
        else:
            role_hint = ("你开口约她。她说「随便」，但真的会来。"
                         "她不会表现得很高兴，但会问「几点的车」。")
    unplanned_hint = "今天就是那一天。" if unplanned_today else "今天不用硬塞。"

    _summary = bible.get("summary") or []
    _facts = bible.get("facts") or []
    _threads = bible.get("threads") or []

    prompt = DAY_PROMPT.format(
        character=character, user_name=profile.get("name") or "（不知道）",
        user_likes="、".join(profile.get("likes") or []) or "（不知道）",
        user_state=profile.get("state") or "（不知道）",
        user_mood=profile.get("mood") or "（不知道）",
        user_attitude=profile.get("attitude") or "（不知道）",
        intimacy=profile.get("intimacy", 30), trust=profile.get("trust", 50),
        city=city, places="、".join(places),
        origin=origin, role_hint=role_hint,
        summary=("\n".join(_summary) if _summary else "（这是第一天）"),
        facts=("\n".join("- " + f for f in _facts) if _facts else "（还没有）"),
        threads=("\n".join("- " + t.get("text", "") for t in _threads)
                 if _threads else "（还没有）"),
        unplanned_hint=unplanned_hint,
        day=day, total=total, role=role, scenes=_scenes_per_day,
    )
    raw, tok = _call(cli, model, prompt, max_tokens=900)
    d = _parse(raw)
    d.setdefault("day", day)
    d.setdefault("role", role)
    d.setdefault("threads_out", [])
    print(f"  [外层] 第 {day} 天「{d.get('title')}」 {tok} token", flush=True)
    return d, tok


def generate_scene(cli, model, character, profile, day_plan, scene_idx,
                   previous, bg, n_lines, has_choice, total_scenes, next_scene,
                   facts=None, beat="", written=None, char_name="她"):
    day_json = json.dumps(
        {k: day_plan.get(k) for k in
         ("title", "outline", "unplanned", "awkward", "object", "change", "places")},
        ensure_ascii=False, indent=2)

    scene_hint = "这是今天的最后一幕，要有落点。" if scene_idx == total_scenes else \
                 "这一幕往下推，留一个钩子。"
    branch_hint = ""
    if has_choice:
        if next_scene:
            branch_hint = ('7. 这一幕有选择点。两个选项的 reply 要明显不同，'
                           '但 next 都写 "d%ds%d"（下一幕），不要写成分叉。'
                           % (day_plan["day"], next_scene))
        else:
            branch_hint = ('7. 这一幕有选择点，是今天的最后一幕。'
                           '两个选项的 reply 要明显不同，next 一律写空字符串 ""。')

    prompt = SCENE_PROMPT.format(
        character=character, day_json=day_json,
        user_name=profile.get("name") or "（不知道）",
        user_likes="、".join(profile.get("likes") or []) or "（不知道）",
        user_state=profile.get("state") or "（不知道）",
        intimacy=profile.get("intimacy", 30),
        previous=previous or "（这是今天第一幕）",
        bg=bg, n_lines=n_lines, scene_hint=scene_hint,
        facts=("\n".join("- " + f for f in (facts or [])) if facts else "（还没有）"),
        beat=(beat or "把这一天往前推一步"),
        written=("\n".join("- " + w for w in (written or [])) if written else "（这是今天第一幕）"),
        char_name=char_name or "她",
        bgs="、".join(VALID_BG),
        branch_hint=branch_hint,
        day=day_plan["day"], scene=scene_idx,
        next_scene=next_scene or 0,
    )
    raw, tok = _call(cli, model, prompt, max_tokens=1800)
    s = _parse(raw)
    # 清掉无效的 next（比如模型写了 d2s0）
    _valid = {"d%ds%d" % (day_plan["day"], i) for i in range(1, total_scenes + 1)}
    for _c in (s.get("choices") or []):
        if isinstance(_c, dict):
            _n = (_c.get("next") or "").strip()
            if _n and _n not in _valid:
                _c["next"] = ""

    s.setdefault("id", "d%ds%d" % (day_plan["day"], scene_idx))
    s.setdefault("bg", bg)
    s.setdefault("lines", [])
    if not has_choice:
        s["choices"] = []
    print(f"    [内层] d{day_plan['day']}s{scene_idx}  {len(s['lines'])} 行  {tok} token", flush=True)
    return s, tok


def build_story(city="杭州", days=7, per_day=3, lines_per_scene=12,
                profile=None, model="deepseek-chat", character_key="浮波柚叶",
                places=None, origin=None, progress_cb=None,
                character_text=None, char_name=None):
    """生成一部多天的短篇。

    核心是 story bible：事实、线索、每天的摘要。
    它保证第 7 天还知道"那把伞第 1 天就断了"。
    """
    profile = dict(DEFAULT_PROFILE, **(profile or {}))
    # 优先用传进来的人设（peini 里那个角色的完整 prompt）
    # 截到 1200 字：完整人设 1600+ 字，乘 28 次调用就是白烧一半 token
    _ct = (character_text or "").strip()
    if len(_ct) > 1100:
        # 不能硬砍 —— 砍掉"你怎么说话"那一段，语气就散了。
        # 先找说话方式那一段，保下来，再补开头。
        import re as _re
        m = _re.search(r"##\s*你怎么说话.*?(?=\n##|$)", _ct, _re.S)
        style = m.group(0)[:520] if m else ""
        head = _ct[:520]
        _ct = (head + "\n\n" + style).strip()[:1100]
    character = _ct or CHARACTERS.get(character_key, CHARACTERS["浮波柚叶"])

    # 台词挂谁名下：优先用传进来的名字
    char_name = (char_name or character_key or "她").strip()
    if char_name.startswith("custom:"):
        char_name = "她"
    places = places or HANGZHOU

    _progress_cb = progress_cb
    cli = _client()
    total_tok = 0
    _degrade_count = {"n": 0}
    out_days = []

    # 故事圣经：跨天不变的东西
    bible = {"facts": [], "threads": [], "summary": []}

    # 出发地：没给就按"和目的地重合"处理 → 新艾利都
    if not origin or origin == city:
        origin = "新艾利都"

    roles = dict(day_roles(days))
    print("  出发地：%s → 目的地：%s" % (origin, city), flush=True)
    print("  日程：%s" % "、".join("%d.%s" % (d, roles[d]) for d in sorted(roles)),
          flush=True)

    # 计划外的事：第 3 天和倒数第 3 天（"来"和"返程"不塞意外）
    play_days = [d for d in sorted(roles) if roles[d] == "玩"]
    unplanned_days = set()
    if play_days:
        unplanned_days.add(play_days[len(play_days) // 2])
    if len(play_days) >= 3:
        unplanned_days.add(play_days[1])

    bgs = ["bg_station", "bg_street", "bg_lake", "bg_room", "bg_night"]

    for day in range(1, days + 1):
        print(f"\n=== 第 {day} 天 ===", flush=True)
        plan, tok = generate_day(cli, model, character, profile, city,
                                 day, days, bible, places,
                                 unplanned_today=(day in unplanned_days),
                                 role=roles[day], origin=origin,
                                 scenes_per_day=per_day)
        total_tok += tok

        # 这一天每一幕要完成什么（外层给的）
        beats = plan.get("beats") or []
        if not isinstance(beats, list):
            beats = []
        while len(beats) < per_day:
            beats.append("")

        scenes = []
        written = []
        prev_line = ""
        for si in range(1, per_day + 1):
            _role = roles[day]
            if _role == "邀约":
                bg = "bg_night" if si == 1 else "bg_room"
            elif _role == "来":
                bg = "bg_station" if si <= 2 else "bg_street"
            elif _role == "返程":
                bg = "bg_street" if si <= 2 else "bg_station"
            elif _role == "送别":
                bg = "bg_station"
            else:
                if si == per_day:
                    bg = "bg_room"
                else:
                    bg = bgs[(day + si) % len(bgs)]
                    if bg in ("bg_station", "bg_room"):
                        bg = "bg_lake"

            has_choice = (si == per_day and day < days)
            next_scene = si + 1 if si < per_day else 0

            try:
                sc, tok = generate_scene(cli, model, character, profile, plan, si,
                                         prev_line, bg, lines_per_scene,
                                         has_choice, per_day, next_scene,
                                         facts=bible["facts"],
                                         beat=beats[si - 1] if si - 1 < len(beats) else "",
                                         written=written,
                                         char_name=char_name)
            except Exception as _se:
                # 这一幕三次都失败了：降级成短的一幕，不要整单死
                _fails = _degrade_count.get("n", 0) + 1
                _degrade_count["n"] = _fails
                print("    [降级] d%ds%d 失败：%s" % (day, si, str(_se)[:60]), flush=True)
                if _fails >= 3:
                    raise RuntimeError("连续降级 %d 次，模型那边有问题" % _fails)
                sc = {
                    "id": "d%ds%d" % (day, si),
                    "bg": bg,
                    "lines": [
                        {"who": "", "bg": bg,
                         "text": (prev_line or plan.get("outline") or "路上没说什么。")[:60]},
                        {"who": char_name, "text": "……"},
                    ],
                    "choices": [],
                    "end": "",
                }
                tok = 0
            total_tok += tok
            scenes.append(sc)

            # 记下这一幕写了什么，下一幕不许重演
            _ls = [x.get("text", "") for x in (sc.get("lines") or []) if x.get("text")]
            if _ls:
                # 传末两句，下一幕才看得清"已经到哪了"
                _tail = " ／ ".join(x[:26] for x in _ls[-2:])
                written.append("第%d幕结尾：%s" % (si, _tail))
                prev_line = _ls[-1][:40]

        plan["scenes"] = scenes
        out_days.append(plan)

        # 进度回调：外面能显示"第几天 / 共几天"
        if _progress_cb:
            try:
                _progress_cb(day, days, total_tok)
            except Exception:
                pass

        # ---- 更新圣经 ----
        summ = (plan.get("summary") or plan.get("outline") or "")[:60]
        bible["summary"].append("第%d天：%s" % (day, summ))

        for f in (plan.get("facts_new") or []):
            f = str(f).strip()
            if f and f not in bible["facts"]:
                bible["facts"].append(f)
        bible["facts"] = bible["facts"][-18:]   # 只留最近的，防止提示词爆炸

        closed = {str(x).strip() for x in (plan.get("threads_closed") or [])}
        bible["threads"] = [x for x in bible["threads"]
                            if x.get("text") not in closed]
        existing = {x.get("text") for x in bible["threads"]}
        for tx in (plan.get("threads_out") or []):
            tx = str(tx).strip()
            if tx and tx not in existing:
                bible["threads"].append({"text": tx, "since": day})
        bible["threads"] = bible["threads"][-8:]

        print("    [圣经] 事实 %d 条，线索 %d 条" %
              (len(bible["facts"]), len(bible["threads"])), flush=True)

    total_lines = sum(len(s["lines"]) for d in out_days for s in d["scenes"])
    story = {
        "city": city,
        "origin": origin,
        "roles": {str(d): roles[d] for d in roles},
        "character": character_key,
        "profile": profile,
        "days": out_days,
        "bible": bible,
        "meta": {
            "model": model,
            "tokens": total_tok,
            "cost": round((total_tok / 1_000_000) * 10, 4),
            "days": days,
            "scenes_per_day": per_day,
            "lines_per_scene": lines_per_scene,
            "total_lines": total_lines,
        },
    }
    return story


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="杭州")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--scenes", type=int, default=3)
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--lines", type=int, default=12)
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "story.json"))
    ap.add_argument("--profile", default="", help="画像 JSON 文件")
    args = ap.parse_args()

    profile = {}
    if args.profile and os.path.exists(args.profile):
        profile = json.load(open(args.profile, encoding="utf-8-sig"))

    story = build_story(args.city, args.days, args.scenes, args.lines,
                        profile, args.model)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    print(f"\n已保存 {args.out}")
    m = story["meta"]
    print(f"token {m['tokens']}  费用约 {m['cost']} 元")
    print(f"共 {m['days']} 天 × {m['scenes_per_day']} 幕，{m['total_lines']} 段对话")
    print()
    for d in story["days"]:
        print(f"  第{d['day']}天「{d.get('title')}」 {len(d['scenes'])} 幕")
        print(f"    {d.get('outline','')[:60]}")
        print(f"    计划外：{d.get('unplanned','')[:50]}")
        print(f"    变化：{d.get('change','')[:50]}")


if __name__ == "__main__":
    main()
