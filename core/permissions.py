# core/permissions.py
# 权限分级：四种人 + 一套能力表。
#
# 为什么不做 Lv1-Lv10 等级制：
#   1. "怎么升级"要另外定义一套规则，迟早和好感度、余额打架
#   2. 权限判断写成 level >= 5，以后加一种人就得重排号
#   3. 实际上只有四种人
#
# 一条产品原则（写在代码里提醒自己）：
#   用额度控成本，不用权限锁功能。
#   免费用户的功能必须完整，否则早期留存会被弹窗杀死。

ROLES = {
    #         显示名   日额度(元)  能用游戏  能聊天
    "user":   {"name": "普通", "daily_limit": 0.30, "games": True,  "can_chat": True},
    "vip":    {"name": "老友", "daily_limit": 3.00, "games": True,  "can_chat": True},
    "admin":  {"name": "内部", "daily_limit": None, "games": True,  "can_chat": True},
    "banned": {"name": "停用", "daily_limit": 0.0,  "games": False, "can_chat": False},
}

DEFAULT_ROLE = "user"


def get_role(user) -> str:
    """从 users 表的一行里取角色。未知值一律当普通用户，不让配置错误把人锁死。"""
    role = (user or {}).get("role") or DEFAULT_ROLE
    return role if role in ROLES else DEFAULT_ROLE


def role_name(user) -> str:
    return ROLES[get_role(user)]["name"]


def can_chat(user) -> bool:
    return ROLES[get_role(user)]["can_chat"]


def can_use_games(user) -> bool:
    return ROLES[get_role(user)]["games"]


def daily_limit(user):
    """日额度。个人设置优先于角色默认；返回 None 表示不限。"""
    personal = (user or {}).get("daily_limit")
    if personal is not None:
        return float(personal)
    return ROLES[get_role(user)]["daily_limit"]


def is_admin(user) -> bool:
    return get_role(user) == "admin"


def is_vip(user) -> bool:
    return get_role(user) in ("vip", "admin")
