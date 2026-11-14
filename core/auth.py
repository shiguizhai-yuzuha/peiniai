import uuid
import bcrypt


def hash_password(password: str) -> str:
    """把明文密码哈希"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def new_user_id() -> str:
    """生成新的 user_id"""
    return str(uuid.uuid4())


def validate_username(username: str) -> tuple[bool, str]:
    """校验用户名：3-20 位英文数字下划线"""
    if not username:
        return False, "用户名不能为空"
    if len(username) < 3 or len(username) > 20:
        return False, "用户名长度需 3-20 位"
    if not all(c.isalnum() or c == "_" for c in username):
        return False, "用户名只能包含字母、数字、下划线"
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """校验密码：至少 6 位"""
    if not password:
        return False, "密码不能为空"
    if len(password) < 6:
        return False, "密码至少 6 位"
    return True, ""