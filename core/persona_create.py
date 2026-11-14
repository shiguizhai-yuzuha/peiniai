# -*- coding: utf-8 -*-
"""新建私有角色：校验 / 导入 / 生成 / 写库

这四步跟界面无关，所以放在 core 里。
界面和状态（gr.update、背景、首个会话）留在 app.py。

约定：所有函数不抛异常，错误用字符串返回。
"""

from core import personas, persona_gen, chat_import
from db import repository as repo
from services import billing

COST_HINT = "⚠️ 余额不够了。建一个角色大约 0.012 元。"
LIMIT_HINT = ("⚠️ 你已经有她了。\n\n"
              "想换一个，先点下面的「删掉现在那个」。")


def check(name, quote, user_id):
    """动手之前的检查。通过返回 None。"""
    if not user_id:
        return "⚠️ 请先登录。"
    if not (name or "").strip():
        return "⚠️ 先给她一个名字。"
    if not (quote or "").strip():
        return "⚠️ 至少写一句她说过的原话——这一项最关键。"
    if repo.count_custom_personas(user_id) >= 1:
        return LIMIT_HINT
    if not billing.has_balance(user_id):
        return COST_HINT
    return None


def import_chat(user_id, raw, call_me):
    """从聊天记录里提炼她的语气和共同经历。没有材料就返回 None。"""
    if not (raw or "").strip():
        return None
    try:
        imported = chat_import.extract(raw, my_name=(call_me or ""))
        billing.charge(user_id, imported.get("prompt_tokens", 0),
                       imported.get("completion_tokens", 0))
        repo.add_tokens(user_id, imported.get("tokens", 0))
        print("[导入] 轮数=%s 置信=%s token=%s"
              % (imported.get("turns"), imported.get("confidence"),
                 imported.get("tokens")), flush=True)
        return imported
    except Exception as e:
        print("[导入] 失败，跳过：%s" % e, flush=True)
        return None


def generate(user_id, name, call_me, quote, state, target, imported):
    """调模型生成人设，计费，并把导入的信息并进去。返回 (r, error)。"""
    _quote = quote.strip()
    if imported and imported.get("her_lines"):
        _quote = imported["her_lines"][0]

    try:
        r = persona_gen.generate(name.strip(), call_me.strip(), _quote, state, target)
        billing.charge(user_id, r.get("prompt_tokens", 0),
                       r.get("completion_tokens", 0))
        repo.add_tokens(user_id, r.get("tokens", 0))
        print("[新建角色] 计费 prompt=%s completion=%s"
              % (r.get("prompt_tokens"), r.get("completion_tokens")), flush=True)
    except Exception as e:
        return None, f"⚠️ 生成失败：{e}"

    if imported:
        extra = []
        if imported.get("her_style"):
            extra.append("## 你的说话方式（从聊天记录里学到的）\n" + imported["her_style"])
        if imported.get("her_lines"):
            extra.append("## 你说过的话\n" + "\n".join("「%s」" % x for x in imported["her_lines"]))
        if imported.get("shared"):
            extra.append("## 你们的共同经历\n" + "\n".join("- " + x for x in imported["shared"]))
        if extra:
            r["prompt"] = r["prompt"] + "\n\n" + "\n\n".join(extra)
        if imported.get("her_lines"):
            r["catchphrases"] = (imported["her_lines"][:3] + r["catchphrases"])[:6]

    return r, None


def save(user_id, name, call_me, target, r, imported):
    """写库：角色本体 + 初始状态 + 初始好感 + 共同经历。

    返回 (cid, knows, stage, error)。
    """
    try:
        cid = repo.create_custom_persona(
            user_id,
            name=name.strip(),
            call_me=call_me.strip(),
            prompt=r["prompt"],
            opening=r["opening"],
            catchphrases="|".join(r["catchphrases"]),
            target=target,
        )

        # 初始开关：复合 / 恋爱 → 她不知道已结束；告别 → 她知道了
        knows = 1 if target == "告别" else 0
        stage = "C" if knows else "A"
        repo.update_custom_persona(cid, knows=knows, stage=stage)

        # 初始好感：记忆是满的，关系是空的
        # 她记得你们的一切，但温度要重来——手不会主动伸过来，话说一半会收回去
        intimacy, trust = 50, 50.0
        repo.set_character_baseline(user_id, personas.custom_key(cid),
                                    intimacy=intimacy, trust=trust)
        print("[新建角色] 初始好感 intimacy=%s trust=%s" % (intimacy, trust), flush=True)

        # 聊天记录里的共同经历，直接写成记忆（标明来源）
        if imported and imported.get("shared"):
            for i, s in enumerate(imported["shared"][:8]):
                repo.upsert_memory(user_id, personas.custom_key(cid),
                                   "moment:imported%d" % i, s, priority=6)
        return cid, knows, stage, None
    except Exception as e:
        return None, None, None, f"⚠️ 保存失败：{e}"
