NEGATIVE_WORDS = ["难过", "伤心", "累", "烦", "哭", "崩溃", "孤独", "焦虑"]
POSITIVE_WORDS = ["开心", "高兴", "爽", "喜欢", "爱", "棒", "谢谢"]


def score(text: str) -> float:
    """简单情感打分：-1 ~ 1"""
    s = 0.0
    for w in NEGATIVE_WORDS:
        if w in text:
            s -= 0.3
    for w in POSITIVE_WORDS:
        if w in text:
            s += 0.3
    return max(-1.0, min(1.0, s))


def update_emotion(current: float, text: str) -> float:
    """带衰减的情感更新"""
    return current * 0.7 + score(text) * 0.3