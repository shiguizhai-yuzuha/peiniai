from db import repository as repo

# DeepSeek 官方进价（元 / 百万 token）：输入 2.0，输出 8.0
# 这里按 2 倍售价计费 → 毛利率 50%
PRICE_INPUT = 4.0
PRICE_OUTPUT = 16.0
PRICE_PER_IMAGE = 0.05      # 每张图额外扣 5 分


def calc_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens * PRICE_INPUT / 1_000_000
        + completion_tokens * PRICE_OUTPUT / 1_000_000
    )


def charge(user_id: str, prompt_tokens: int, completion_tokens: int):
    cost = calc_cost(prompt_tokens, completion_tokens)
    repo.update_balance(user_id, -cost)
    return cost


def charge_image(user_id: str, count: int = 1) -> float:
    """每张图额外扣费（默认 1 分）。"""
    fee = abs(PRICE_PER_IMAGE) * max(0, int(count))
    if fee:
        repo.update_balance(user_id, -fee)
    return fee


def charge_yuan(user_id: str, amount: float):
    """按元扣。给"一次 5 元"这种定价用，不是按 token。"""
    repo.update_balance(user_id, -abs(amount))
    return abs(amount)


def has_balance(user_id: str, minimum: float = 0.01) -> bool:
    user = repo.get_or_create_user(user_id)
    return user.get("balance", 0) >= minimum