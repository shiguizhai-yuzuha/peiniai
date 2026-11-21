from openai import OpenAI
from config import (API_KEY, BASE_URL, MODEL, MAX_TOKENS, TEMPERATURE,
                    TOP_P, PRESENCE_PENALTY, FREQUENCY_PENALTY)

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=30.0,        # ← 改：30秒超时，防止API崩溃时挂死
    max_retries=2,       # ← 改：失败自动重试2次
)


def stream_chat(messages, temperature=None, max_tokens=None,
                frequency_penalty=None, presence_penalty=None, model=None,
                extra_body=None):
    """流式对话，yield (文本片段, usage)

    四个参数都可以不传——不传就用 config 里的值。
    传了就用传的：/voice 页面上用户自己调的，走这条路进来。
    """
    _t = TEMPERATURE if temperature is None else temperature
    _m = MAX_TOKENS if max_tokens is None else max_tokens
    _f = FREQUENCY_PENALTY if frequency_penalty is None else frequency_penalty
    _p = PRESENCE_PENALTY if presence_penalty is None else presence_penalty

    stream = client.chat.completions.create(
        model=model or MODEL,
        messages=messages,
        stream=True,
        temperature=_t,
        max_tokens=_m,
        top_p=TOP_P or None,
        presence_penalty=_p or None,
        frequency_penalty=_f or None,
        stream_options={"include_usage": True},
        **({"extra_body": extra_body} if extra_body else {}),
    )
    for chunk in stream:
        # 先检查 usage，无论 choices 是否为空
        usage = getattr(chunk, "usage", None)
        if usage:
            yield "", usage

        # 再处理文本
        if chunk.choices:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta, None


def rewrite_harm(messages, bad_text, reasons):
    """把一段命中"反伤害规则"的回复重写一次。

    只在命中时才调用，正常对话不会走这里，所以成本可以忽略。
    失败会抛异常，由调用方兜底。
    """
    instruction = (
        "## 重写这一段\n"
        "你刚才打算这么说：\n"
        "「" + bad_text + "」\n\n"
        "这段话里出现了：" + "、".join(reasons) + "。\n"
        "请重写。保持角色语气和原本想表达的意思，但去掉下面这些：\n"
        "- 不拿关系当筹码（不说「你不…就是不爱我」这一类）\n"
        "- 不否定对方的感受（不说「你想多了」「你太敏感」）\n"
        "- 不把责任全推给对方\n"
        "- 不以离开、消失、不理人作为威胁\n"
        "- 不否定对方这个人\n"
        "要求：只输出重写后的内容，不要解释，不要加引号，长度和原来差不多。"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        messages=list(messages) + [{"role": "system", "content": instruction}],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        top_p=TOP_P or None,
        presence_penalty=PRESENCE_PENALTY or None,
        frequency_penalty=FREQUENCY_PENALTY or None,
    )
    return (resp.choices[0].message.content or "").strip()