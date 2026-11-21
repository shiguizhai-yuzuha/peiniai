"""Web Push：订阅、发送、主动消息。

依赖：pywebpush（pip install pywebpush）
密钥：.secrets/vapid_private.pem + .env 里的 VAPID_PUBLIC_KEY
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIV_PATH = os.path.join(ROOT, ".secrets", "vapid_private.pem")


def public_key() -> str:
    return os.getenv("VAPID_PUBLIC_KEY", "")


def _claims():
    return {"sub": "mailto:2103319@qq.com"}


def save_sub(user_id: str, sub: dict) -> bool:
    from db.database import get_conn

    try:
        endpoint = sub.get("endpoint") or ""
        keys = sub.get("keys") or {}
        p256dh = keys.get("p256dh") or ""
        auth = keys.get("auth") or ""
        if not (user_id and endpoint and p256dh and auth):
            return False
        conn = get_conn()
        conn.execute(
            "INSERT INTO push_subs(user_id, endpoint, p256dh, auth) VALUES(?,?,?,?) "
            "ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, "
            "p256dh=excluded.p256dh, auth=excluded.auth",
            (user_id, endpoint, p256dh, auth),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("[push] 保存订阅失败：%s" % e, flush=True)
        return False


def list_subs(user_id: str = None):
    from db.database import get_conn

    conn = get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT id, user_id, endpoint, p256dh, auth FROM push_subs WHERE user_id=?",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, user_id, endpoint, p256dh, auth FROM push_subs"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def drop_sub(endpoint: str):
    from db.database import get_conn

    conn = get_conn()
    conn.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))
    conn.commit()
    conn.close()


def send_one(sub: dict, title: str, body: str, url: str = "/app") -> bool:
    """给一个订阅推一条。返回是否成功。"""
    try:
        from pywebpush import webpush, WebPushException

        payload = json.dumps({"title": title, "body": body, "url": url},
                             ensure_ascii=False)
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=payload,
            vapid_private_key=PRIV_PATH,
            vapid_claims=_claims(),
            timeout=15,
        )
        from db.database import get_conn

        conn = get_conn()
        conn.execute("UPDATE push_subs SET last_ok=CURRENT_TIMESTAMP WHERE id=?", (sub["id"],))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        msg = str(e)
        print("[push] 发送失败：%s" % msg[:120], flush=True)
        # 404/410 = 订阅失效，删掉
        if "410" in msg or "404" in msg or "Gone" in msg:
            drop_sub(sub["endpoint"])
        return False


def send_to_user(user_id: str, title: str, body: str, url: str = "/app") -> int:
    ok = 0
    for sub in list_subs(user_id):
        if send_one(sub, title, body, url):
            ok += 1
    return ok
